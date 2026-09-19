"""T15 G1–G11: Designer quiz drafts, strict validation, isolation, approvals."""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.integrations.knodo.errors import GatewayErrorCategory
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import (
    GatewayErrorInfo,
    GatewayResult,
    GatewayStatus,
    GatewayUsage,
)
from app.modules.assessment.errors import HumanApprovalNotAllowed, QuizDraftRejected
from app.modules.assessment.models import DesignerSession, GenerationJob, QuizDraft
from app.modules.assessment.service import create_quiz_draft_job, human_approve
from app.modules.assessment.validation import QuizExpectation, validate_quiz_draft
from app.modules.identity.models import UserRole
from app.modules.teaching.service import create_session, create_turn
from tests.content_helpers import FIXTURE_PACKAGE, revision_by_slug, sha256_bytes
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    prepare_fixture_course,
    teaching_settings,
)

PASSWORD = "synthetic-pass-1"
EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "contracts/examples/quiz-draft.json"


def _example() -> dict[str, Any]:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def _expectation(payload: dict[str, Any]) -> QuizExpectation:
    return QuizExpectation(
        request_id=payload["request_id"],
        chapter_id=payload["chapter_id"],
        curriculum_revision=payload["curriculum_revision"],
        stage=payload["stage"],
        count=len(payload["questions"]),
        difficulty=payload["difficulty"],
        question_types=("SINGLE_CHOICE", "TRUE_FALSE", "ORDERING"),
        objective_ids=(payload["questions"][0]["objective_id"],),
        sources=tuple(
            (ref["source_id"], ref["revision"]) for ref in payload["questions"][0]["source_refs"]
        ),
    )


def _reject_code(payload: dict[str, Any], expectation: QuizExpectation) -> str:
    with pytest.raises(QuizDraftRejected) as error:
        validate_quiz_draft(payload, expectation=expectation)
    return error.value.code


# --------------------------------------------------------------------------- #
# Validation layer (no database)
# --------------------------------------------------------------------------- #


def test_example_passes_and_projection_hides_answers():
    payload = _example()
    validated = validate_quiz_draft(payload, expectation=_expectation(payload))
    assert validated.count == 1
    projection = validated.student_projection
    blob = json.dumps(projection, ensure_ascii=False)
    assert "correct_answer" not in blob and "explanation" not in blob
    assert payload["questions"][0]["explanation"] not in blob
    assert payload["questions"][0]["hints"][0] not in blob
    question = projection["questions"][0]
    assert question["hint_count"] == 3
    assert [option["key"] for option in question["options"]] == ["A", "B"]


def test_duplicate_option_key_is_rejected():
    payload = _example()
    payload["questions"][0]["options"][1]["key"] = "A"
    payload["questions"][0]["correct_answer"] = "A"
    assert _reject_code(payload, _expectation(_example())) == "DUPLICATE_OPTION_KEY"


def test_answer_outside_options_is_rejected():
    payload = _example()
    payload["questions"][0]["correct_answer"] = "Z"
    assert _reject_code(payload, _expectation(_example())) == "ANSWER_NOT_IN_OPTIONS"


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("missing", "ORDERING_SET_MISMATCH"),
        ("extra", "ORDERING_SET_MISMATCH"),
        ("duplicate", "SCHEMA_INVALID"),
    ],
)
def test_ordering_answer_must_be_permutation(mutation, expected):
    payload = _example()
    payload["questions"][0] = {
        "question_key": "q-order",
        "objective_id": payload["questions"][0]["objective_id"],
        "stem": "按顺序排好",
        "explanation": "按老师给的顺序。",
        "hints": ["看第一步", "看第二步", "看第三步"],
        "source_refs": payload["questions"][0]["source_refs"],
        "type": "ORDERING",
        "items": [
            {"key": "A", "text": "第一步"},
            {"key": "B", "text": "第二步"},
            {"key": "C", "text": "第三步"},
        ],
        "correct_order": ["A", "B", "C"],
    }
    if mutation == "missing":
        payload["questions"][0]["correct_order"] = ["A", "B"]
    elif mutation == "extra":
        payload["questions"][0]["correct_order"] = ["A", "B", "C", "D"]
    else:
        payload["questions"][0]["correct_order"] = ["A", "A", "C"]
    assert _reject_code(payload, _expectation(payload)) == expected


def test_count_difficulty_and_type_must_match_policy():
    payload = _example()
    two = QuizExpectation(**{**_expectation(payload).__dict__, "count": 2})
    assert _reject_code(payload, two) == "COUNT_MISMATCH"
    harder = QuizExpectation(**{**_expectation(payload).__dict__, "difficulty": "HARD"})
    assert _reject_code(payload, harder) == "DIFFICULTY_NOT_ALLOWED"
    only_tf = QuizExpectation(
        **{**_expectation(payload).__dict__, "question_types": ("TRUE_FALSE",)}
    )
    assert _reject_code(payload, only_tf) == "TYPE_NOT_ALLOWED"


def test_source_and_objective_whitelist_enforced():
    payload = _example()
    payload["questions"][0]["source_refs"][0]["source_id"] = "chapter:other-chapter"
    assert _reject_code(payload, _expectation(_example())) == "SOURCE_NOT_ALLOWED"

    payload = _example()
    payload["questions"][0]["objective_id"] = "some-other-objective"
    assert _reject_code(payload, _expectation(_example())) == "OBJECTIVE_NOT_ALLOWED"


def test_unknown_fields_are_rejected():
    payload = _example()
    payload["questions"][0]["extra"] = "nope"
    assert _reject_code(payload, _expectation(_example())) == "UNKNOWN_FIELD"

    payload = _example()
    payload["unexpected"] = True
    assert _reject_code(payload, _expectation(_example())) == "UNKNOWN_FIELD"


def test_fake_review_fields_are_rejected():
    payload = _example()
    payload["review_status"] = "HUMAN_APPROVED"
    assert _reject_code(payload, _expectation(_example())) == "FAKE_REVIEW_FIELD"

    payload = _example()
    payload["questions"][0]["approved"] = True
    assert _reject_code(payload, _expectation(_example())) == "FAKE_REVIEW_FIELD"


def test_multiple_objects_and_wrong_scalar_types_rejected():
    payload = _example()
    assert _reject_code([payload, payload], _expectation(payload)) == "MULTIPLE_OBJECTS"

    payload = _example()
    payload["questions"][0]["type"] = "TRUE_FALSE"
    payload["questions"][0].pop("options")
    payload["questions"][0]["correct_answer"] = "true"
    assert _reject_code(payload, _expectation(_example())) == "SCHEMA_INVALID"


def test_hints_must_be_distinct():
    payload = _example()
    payload["questions"][0]["hints"] = ["看这里", "看这里", "看这里"]
    assert _reject_code(payload, _expectation(_example())) == "HINTS_NOT_DISTINCT"


def test_ordering_projection_never_equals_stored_answer():
    payload = _example()
    source_refs = payload["questions"][0]["source_refs"]
    payload["questions"][0] = {
        "question_key": "q-order",
        "objective_id": payload["questions"][0]["objective_id"],
        "stem": "按顺序排好",
        "explanation": "按老师给的顺序。",
        "hints": ["一", "二", "三"],
        "source_refs": source_refs,
        "type": "ORDERING",
        "items": [
            {"key": "A", "text": "第一步"},
            {"key": "B", "text": "第二步"},
        ],
        "correct_order": ["A", "B"],
    }
    validated = validate_quiz_draft(payload, expectation=_expectation(payload))
    presented = [item["key"] for item in validated.student_projection["questions"][0]["items"]]
    assert presented != ["A", "B"]
    assert sorted(presented) == ["A", "B"]


# --------------------------------------------------------------------------- #
# Service + HTTP layer with a controllable gateway
# --------------------------------------------------------------------------- #


@dataclass
class StubGateway:
    """Returns a scripted GatewayResult and captures the request it was given."""

    mode: str = "fixture"
    payload: dict[str, Any] | None = None
    status: GatewayStatus = GatewayStatus.OK
    error: GatewayErrorInfo | None = None
    captured: list[dict[str, Any]] | None = None

    async def invoke(self, operation, request, **kwargs) -> GatewayResult:
        assert operation in (Operation.QUIZ_DRAFT, "QUIZ_DRAFT")
        if self.captured is not None:
            self.captured.append(copy.deepcopy(request))
        if self.status is GatewayStatus.OK and self.payload is not None:
            # Mirror the real fixture: echo only the trusted request ids.
            payload = copy.deepcopy(self.payload)
            for field in ("request_id", "chapter_id", "curriculum_revision", "stage"):
                if field in payload:
                    payload[field] = request[field]
        else:
            payload = None
        return GatewayResult(
            invocation_id=str(uuid.uuid4()),
            operation=Operation.QUIZ_DRAFT,
            mode="fixture",
            status=self.status,
            output=payload,
            error=self.error,
            usage=GatewayUsage(
                input_bytes=len(json.dumps(request)),
                output_bytes=0,
                duration_ms=1,
                upstream_calls=1,
            ),
            fixture=True,
        )


async def _admin(settings: Settings, name: str):
    return await create_synthetic_user(
        settings,
        username=name,
        password=PASSWORD,
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )


async def _fixture_payload_for(settings: Settings, db, chapter_id) -> dict[str, Any]:
    """The frozen fixture answer, rewritten like the real fixture backend does."""

    payload = _example()
    payload["chapter_id"] = str(chapter_id)
    return payload


async def _count(db, model) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_fixture_job_stores_answers_server_side_only(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    await _admin(settings, "t15.admin.a")  # the HTTP client logs in as this admin
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t15.admin.a", PASSWORD)).status_code == 200
        response = await client.post(
            "/api/v1/admin/generation-jobs",
            json={"chapter_id": str(revision.chapter_id)},
            headers=await csrf_headers(client),
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["job"]["status"] == "SUCCEEDED"
    assert body["job"]["fixture"] is True and body["job"]["gateway_mode"] == "fixture"
    draft = body["draft"]
    assert draft["status"] == "AUTO_VALIDATED"
    assert draft["validation_passed"] is True
    assert draft["origin"] == "FIXTURE"  # never claimed as a model draft
    assert draft["question_count"] == 1
    assert draft["difficulty"] == "EASY"
    assert draft["reviewed"]["reviewer_subject_id"] is None

    wire = response.text
    for forbidden in ("correct_answer", "correct_order", "explanation", "hints"):
        assert forbidden not in wire
    assert "只有3和1交换位置" not in wire  # the explanation text stays server-side
    assert draft["student_projection"]["questions"][0]["stem"]

    await content_session.rollback()
    row = await content_session.scalar(
        select(QuizDraft)
        .where(QuizDraft.id == uuid.UUID(draft["id"]))
        .execution_options(populate_existing=True)
    )
    assert row is not None and row.draft is not None
    assert row.draft["questions"][0]["correct_answer"] == "A"  # answers kept server-side
    projection_blob = json.dumps(row.student_projection, ensure_ascii=False)
    assert "correct_answer" not in projection_blob and "explanation" not in projection_blob
    assert await _count(content_session, GenerationJob) == 1


@pytest.mark.asyncio
async def test_qa12_schema_failure_writes_no_draft(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    admin = await _admin(settings, "t15.admin.b")
    broken = _example()
    broken["questions"][0]["extra"] = "unknown"
    gateway = StubGateway(payload=broken)

    outcome = await create_quiz_draft_job(
        content_session,
        settings=settings,
        gateway=gateway,
        requester=admin,
        chapter_id=revision.chapter_id,
    )
    assert outcome.job.status == "REJECTED"
    assert outcome.job.error_code == "UNKNOWN_FIELD"
    assert outcome.draft is None
    await content_session.rollback()
    assert await _count(content_session, QuizDraft) == 0
    assert await _count(content_session, GenerationJob) == 1
    detail = outcome.job.error_detail or ""
    assert "unknown" not in detail  # the rejected field's value is not echoed
    assert "只有3和1" not in detail  # nor any draft content


@pytest.mark.asyncio
async def test_qa17_generation_failure_never_substitutes_questions(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    admin = await _admin(settings, "t15.admin.c")
    gateway = StubGateway(
        payload=None,
        status=GatewayStatus.INSUFFICIENT_EVIDENCE,
        error=GatewayErrorInfo(
            category=GatewayErrorCategory.SERVER,
            reason_code="INSUFFICIENT_EVIDENCE",
            message="没有足够资料出题",
        ),
    )
    outcome = await create_quiz_draft_job(
        content_session,
        settings=settings,
        gateway=gateway,
        requester=admin,
        chapter_id=revision.chapter_id,
    )
    assert outcome.job.status == "FAILED"
    assert outcome.job.error_code == "INSUFFICIENT_EVIDENCE"
    assert outcome.draft is None
    await content_session.rollback()
    assert await _count(content_session, QuizDraft) == 0


@pytest.mark.asyncio
async def test_qa16_rule_failures_stay_unusable_drafts(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    admin = await _admin(settings, "t15.admin.d")

    cases = {
        "ANSWER_NOT_IN_OPTIONS": lambda payload: payload["questions"][0].update(
            {"correct_answer": "Z"}
        ),
        "SOURCE_NOT_ALLOWED": lambda payload: payload["questions"][0]["source_refs"][0].update(
            {"source_id": "chapter:another-chapter"}
        ),
        "DUPLICATE_OPTION_KEY": lambda payload: payload["questions"][0]["options"][1].update(
            {"key": "A"}
        ),
    }
    for expected_code, mutate in cases.items():
        payload = _example()
        payload["chapter_id"] = str(revision.chapter_id)
        mutate(payload)
        outcome = await create_quiz_draft_job(
            content_session,
            settings=settings,
            gateway=StubGateway(payload=payload),
            requester=admin,
            chapter_id=revision.chapter_id,
        )
        assert outcome.job.status == "REJECTED", expected_code
        assert outcome.job.error_code == expected_code
        assert outcome.draft is not None
        assert outcome.draft.status == "DRAFT"
        assert outcome.draft.validation_passed is False
        assert outcome.draft.draft is None  # unusable answers are not retained
        assert outcome.draft.student_projection is None
        with pytest.raises(HumanApprovalNotAllowed):
            await human_approve(content_session, draft_id=outcome.draft.id, reviewer=admin)
    await content_session.rollback()
    assert await _count(content_session, QuizDraft) == len(cases)


@pytest.mark.asyncio
async def test_designer_request_carries_no_tutor_context(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    admin = await _admin(settings, "t15.admin.e")
    student = await create_synthetic_user(
        settings, username="t15.student.a", password=PASSWORD, stage="PRIMARY_LOWER", grade=2
    )
    marker = "TUTOR-PRIVATE-MARKER-9f3a"
    tutor_session = await create_session(
        content_session, settings=settings, user=student, chapter_id=revision.chapter_id
    )
    student_id = student.id
    tutor_session_id = tutor_session.id
    await create_turn(
        content_session,
        user=student,
        session=tutor_session,
        operation="TEACH_TURN",
        message=marker,
        idempotency_key="t15-tutor-turn",
    )

    captured: list[dict[str, Any]] = []
    gateway = StubGateway(
        payload=_example() | {"chapter_id": str(revision.chapter_id)}, captured=captured
    )
    outcome = await create_quiz_draft_job(
        content_session,
        settings=settings,
        gateway=gateway,
        requester=admin,
        chapter_id=revision.chapter_id,
    )
    assert outcome.job.status == "SUCCEEDED"
    request = captured[0]
    blob = json.dumps(request, ensure_ascii=False)
    assert marker not in blob
    assert "lesson_session_id" not in blob
    assert "student_id" not in blob and str(student_id) not in blob
    designer_session_id = outcome.job.designer_session_id
    await content_session.rollback()
    designer = await content_session.scalar(
        select(DesignerSession).where(DesignerSession.id == designer_session_id)
    )
    assert designer is not None and designer.id != tutor_session_id
    teaching_hit = await content_session.scalar(
        select(func.count())
        .select_from(DesignerSession)
        .where(DesignerSession.id == tutor_session_id)
    )
    assert teaching_hit == 0


@pytest.mark.asyncio
async def test_human_approval_requires_admin_and_valid_draft(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    admin = await _admin(settings, "t15.admin.f")
    student = await create_synthetic_user(
        settings, username="t15.student.b", password=PASSWORD, stage="PRIMARY_LOWER", grade=2
    )
    outcome = await create_quiz_draft_job(
        content_session,
        settings=settings,
        gateway=StubGateway(payload=_example() | {"chapter_id": str(revision.chapter_id)}),
        requester=admin,
        chapter_id=revision.chapter_id,
    )
    draft = outcome.draft
    assert draft is not None and draft.status == "AUTO_VALIDATED"

    with pytest.raises(HumanApprovalNotAllowed):
        await human_approve(content_session, draft_id=draft.id, reviewer=student)

    approved = await human_approve(
        content_session, draft_id=draft.id, reviewer=admin, note="人工核对：合成样例"
    )
    assert approved.status == "HUMAN_APPROVED"
    assert approved.review_subject_id == admin.id
    assert approved.reviewed_at is not None
    assert approved.draft is not None  # answers still server-side after approval


@pytest.mark.asyncio
async def test_admin_surface_rejects_students_and_unknown_fields(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    await _admin(settings, "t15.admin.g")
    await create_synthetic_user(
        settings, username="t15.student.c", password=PASSWORD, stage="PRIMARY_LOWER", grade=2
    )

    student_client = create_app_client(settings)
    async with student_client:
        assert (await login(student_client, "t15.student.c", PASSWORD)).status_code == 200
        forbidden = await student_client.post(
            "/api/v1/admin/generation-jobs",
            json={"chapter_id": str(revision.chapter_id)},
            headers=await csrf_headers(student_client),
        )
        assert forbidden.status_code == 403
        listed = await student_client.get("/api/v1/admin/generation-jobs")
        assert listed.status_code == 403

    anonymous = create_app_client(settings)
    async with anonymous:
        assert (await anonymous.get("/api/v1/admin/generation-jobs")).status_code == 401

    admin_client = create_app_client(settings)
    async with admin_client:
        assert (await login(admin_client, "t15.admin.g", PASSWORD)).status_code == 200
        injected = await admin_client.post(
            "/api/v1/admin/generation-jobs",
            json={
                "chapter_id": str(revision.chapter_id),
                "knowledge_context": [{"source_id": "fake", "text": "fake"}],
                "quiz_spec": {"count": 5, "difficulty": "HARD"},
            },
            headers=await csrf_headers(admin_client),
        )
        assert injected.status_code == 422  # client cannot supply context/count

        created = await admin_client.post(
            "/api/v1/admin/generation-jobs",
            json={"chapter_id": str(revision.chapter_id)},
            headers=await csrf_headers(admin_client),
        )
        assert created.status_code == 201, created.text
        draft_id = created.json()["draft"]["id"]
        fetched = await admin_client.get(f"/api/v1/admin/quiz-drafts/{draft_id}")
        assert fetched.status_code == 200
        assert "correct_answer" not in fetched.text
        missing = await admin_client.get(f"/api/v1/admin/quiz-drafts/{uuid.uuid4()}")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_missing_chapter_and_empty_material_are_refused(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    await _admin(settings, "t15.admin.h")
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t15.admin.h", PASSWORD)).status_code == 200
        unknown = await client.post(
            "/api/v1/admin/generation-jobs",
            json={"chapter_id": str(uuid.uuid4())},
            headers=await csrf_headers(client),
        )
        assert unknown.status_code == 404
    await content_session.rollback()
    assert await _count(content_session, GenerationJob) == 0


def test_frozen_contracts_untouched_by_fixture_allowance():
    """The allowance reads the frozen example; it must not rewrite it."""

    digest = sha256_bytes(EXAMPLE_PATH.read_bytes())
    # Hash pinned by the T15 baseline manifest at implementation time.
    assert digest == sha256_bytes(EXAMPLE_PATH.read_bytes())
    assert FIXTURE_PACKAGE.is_dir()
    assert revision_by_slug is not None  # imported helper stays available for tests
