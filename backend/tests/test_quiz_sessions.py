"""T16 H1–H11: immutable quiz snapshots, attempts, hints, review, isolation."""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import func, select, text

from app.config import Settings
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import (
    GatewayResult,
    GatewayStatus,
    GatewayUsage,
)
from app.modules.assessment.models import (
    QuizAttempt,
    QuizDraft,
    QuizHintEvent,
    QuizQuestion,
    QuizReviewLink,
    QuizSession,
)
from app.modules.assessment.service import create_quiz_draft_job
from app.modules.assessment.specs import load_chapter_material
from app.modules.identity.models import UserRole
from app.modules.learning.models import QuizEvidence
from tests.content_helpers import revision_by_slug
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    prepare_fixture_course,
    teaching_settings,
)

PASSWORD = "synthetic-pass-1"


@dataclass
class StubDesignerGateway:
    payload: dict[str, Any]
    captured: list[dict[str, Any]] = field(default_factory=list)

    async def invoke(self, operation, request, **kwargs) -> GatewayResult:
        assert operation in (Operation.QUIZ_DRAFT, "QUIZ_DRAFT")
        self.captured.append(copy.deepcopy(request))
        output = copy.deepcopy(self.payload)
        for key in ("request_id", "chapter_id", "curriculum_revision", "stage"):
            if key in output:
                output[key] = request[key]
        return GatewayResult(
            invocation_id=str(uuid.uuid4()),
            operation=Operation.QUIZ_DRAFT,
            mode="fixture",
            status=GatewayStatus.OK,
            output=output,
            error=None,
            usage=GatewayUsage(
                input_bytes=len(json.dumps(request)),
                output_bytes=0,
                duration_ms=1,
                upstream_calls=1,
            ),
            fixture=True,
        )


def _hints() -> list[str]:
    return ["先读题干", "再找关键词", "最后逐项检查"]


def _single_choice(key: str, objective: str, refs: list[dict], answer: str = "A") -> dict:
    return {
        "question_key": key,
        "objective_id": objective,
        "stem": f"题目 {key}：哪一个是正确做法？",
        "explanation": f"{key} 的解析：按步骤检查即可。",
        "hints": _hints(),
        "source_refs": refs,
        "type": "SINGLE_CHOICE",
        "options": [{"key": "A", "text": "先看再判断"}, {"key": "B", "text": "直接猜"}],
        "correct_answer": answer,
    }


def _true_false(key: str, objective: str, refs: list[dict], answer: bool = True) -> dict:
    return {
        "question_key": key,
        "objective_id": objective,
        "stem": f"题目 {key}：这句话对吗？",
        "explanation": f"{key} 的解析：对照课文即可。",
        "hints": _hints(),
        "source_refs": refs,
        "type": "TRUE_FALSE",
        "correct_answer": answer,
    }


def _ordering(key: str, objective: str, refs: list[dict]) -> dict:
    return {
        "question_key": key,
        "objective_id": objective,
        "stem": f"题目 {key}：按正确顺序排列。",
        "explanation": f"{key} 的解析：顺序是 一→二→三。",
        "hints": _hints(),
        "source_refs": refs,
        "type": "ORDERING",
        "items": [
            {"key": "A", "text": "第一步"},
            {"key": "B", "text": "第二步"},
            {"key": "C", "text": "第三步"},
        ],
        "correct_order": ["A", "B", "C"],
    }


def _source_refs(material) -> list[dict]:
    return [
        {
            "source_id": f"chapter:{material.chapter_slug}",
            "revision": str(material.revision_number),
            "locator": "block:0",
        }
    ]


def _payload(material, questions: list[dict], difficulty: str = "EASY") -> dict:
    return {
        "schema_version": "k12.quiz.draft.v1",
        "request_id": "pending-echo",
        "chapter_id": str(material.chapter_id),
        "curriculum_revision": material.curriculum_revision,
        "stage": material.stage,
        "difficulty": difficulty,
        "questions": questions,
        "warnings": [],
    }


async def _admin(settings: Settings, name: str):
    return await create_synthetic_user(
        settings,
        username=name,
        password=PASSWORD,
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )


async def _junior(settings: Settings, name: str):
    return await create_synthetic_user(
        settings, username=name, password=PASSWORD, stage="JUNIOR", grade=8
    )


async def _primary(settings: Settings, name: str):
    return await create_synthetic_user(
        settings, username=name, password=PASSWORD, stage="PRIMARY_LOWER", grade=2
    )


async def _auto_validated_draft(
    db, settings: Settings, chapter_id, questions, *, difficulty="EASY"
):
    material = await load_chapter_material(db, chapter_id=chapter_id)
    admin = await _admin(settings, f"t16.admin.{uuid.uuid4().hex[:6]}")
    outcome = await create_quiz_draft_job(
        db,
        settings=settings,
        gateway=StubDesignerGateway(_payload(material, questions, difficulty)),
        requester=admin,
        chapter_id=chapter_id,
    )
    assert outcome.job.status == "SUCCEEDED", outcome.job.error_code
    assert outcome.draft is not None
    return outcome.draft, material


async def _open_quiz(client, chapter_id) -> dict:
    response = await client.post(
        "/api/v1/quiz-sessions",
        json={"chapter_id": str(chapter_id)},
        headers=await csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _answer(client, session_id, question_id, answer, key: str):
    return await client.post(
        f"/api/v1/quiz-sessions/{session_id}/questions/{question_id}/answers",
        json={"answer": answer, "idempotency_key": key},
        headers=await csrf_headers(client),
    )


async def _hint(client, session_id, question_id, level: int, key: str):
    return await client.post(
        f"/api/v1/quiz-sessions/{session_id}/questions/{question_id}/hints",
        json={"level": level, "idempotency_key": key},
        headers=await csrf_headers(client),
    )


@pytest.mark.asyncio
async def test_quiz_dto_hides_answers_until_answered(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    junior_chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    material = await load_chapter_material(content_session, chapter_id=junior_chapter.chapter_id)
    refs = _source_refs(material)
    objective = material.objectives[0]
    await _auto_validated_draft(
        content_session,
        settings,
        junior_chapter.chapter_id,
        [
            _single_choice("q1", objective, refs),
            _single_choice("q2", objective, refs),
            _ordering("q3", objective, refs),
        ],
    )
    await _junior(settings, "t16.student.a")

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.a", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, junior_chapter.chapter_id)
        wire = json.dumps(quiz, ensure_ascii=False)
        assert "correct_answer" not in wire and "explanation" not in wire
        assert "reference_solution" not in wire
        assert "按步骤检查即可" not in wire  # explanation text stays server-side
        assert all("feedback" not in question for question in quiz["questions"])
        assert all(question["hints"] == [] for question in quiz["questions"])
        assert quiz["source_kind"] == "AI_DRAFT"
        assert "AI" in quiz["source_label"]
        assert quiz["progress"] == {"answered": 0, "correct": 0, "total": 3}

    await content_session.commit()
    rows = (
        await content_session.scalars(
            select(QuizQuestion)
            .where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
            .order_by(QuizQuestion.position)
        )
    ).all()
    assert [row.question_key for row in rows] == ["q1", "q2", "q3"]
    assert all(row.correct_answer is not None for row in rows)
    assert all(row.explanation for row in rows)

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.a", PASSWORD)).status_code == 200
        answered = await _answer(client, quiz["id"], str(rows[0].id), "A", "t16-dto-0001")
        assert answered.status_code == 200, answered.text
        assert answered.json()["is_correct"] is True
        assert answered.json()["explanation"]
        refreshed = await client.get(f"/api/v1/quiz-sessions/{quiz['id']}")
        body = refreshed.json()
        assert body["questions"][0]["feedback"]["is_correct"] is True
        assert body["questions"][0]["feedback"]["correct_answer"] == "A"
        assert "feedback" not in body["questions"][1]
        assert "feedback" not in body["questions"][2]
        assert body["progress"]["answered"] == 1


@pytest.mark.asyncio
async def test_true_false_and_ordering_scoring_through_api(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    primary_chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    junior_chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    primary_material = await load_chapter_material(
        content_session, chapter_id=primary_chapter.chapter_id
    )
    primary_refs = _source_refs(primary_material)
    await _auto_validated_draft(
        content_session,
        settings,
        primary_chapter.chapter_id,
        [_true_false("tf1", primary_material.objectives[0], primary_refs, answer=True)],
    )
    await _primary(settings, "t16.student.tf")

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.tf", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, primary_chapter.chapter_id)
        await content_session.commit()
        question = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )
        wrong_type = await _answer(client, quiz["id"], str(question.id), "true", "t16-tf-bad-0001")
        assert wrong_type.status_code == 422
        right = await _answer(client, quiz["id"], str(question.id), True, "t16-tf-ok-0001")
        assert right.status_code == 200 and right.json()["is_correct"] is True
        replay = await _answer(client, quiz["id"], str(question.id), True, "t16-tf-ok-0001")
        assert replay.json()["idempotent_replay"] is True
        conflict = await _answer(client, quiz["id"], str(question.id), False, "t16-tf-ok-0001")
        assert conflict.status_code == 409

    # ORDERING on the junior chapter: right set, wrong order → incorrect.
    junior_material = await load_chapter_material(
        content_session, chapter_id=junior_chapter.chapter_id
    )
    junior_refs = _source_refs(junior_material)
    await _auto_validated_draft(
        content_session,
        settings,
        junior_chapter.chapter_id,
        [
            _single_choice("j1", junior_material.objectives[0], junior_refs),
            _single_choice("j2", junior_material.objectives[0], junior_refs),
            _ordering("j3", junior_material.objectives[0], junior_refs),
        ],
    )
    await _junior(settings, "t16.student.ord")
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.ord", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, junior_chapter.chapter_id)
        await content_session.commit()
        questions = (
            await content_session.scalars(
                select(QuizQuestion)
                .where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
                .order_by(QuizQuestion.position)
            )
        ).all()
        ordering = questions[2]
        assert ordering.type == "ORDERING"
        # the presented order is not the answer by construction
        presented = [item["key"] for item in ordering.items]
        assert presented != ordering.correct_answer
        wrong_order = await _answer(
            client, quiz["id"], str(ordering.id), ["B", "A", "C"], "t16-ord-wrong-01"
        )
        assert wrong_order.status_code == 200
        assert wrong_order.json()["is_correct"] is False
        right_order = await _answer(
            client, quiz["id"], str(ordering.id), ["A", "B", "C"], "t16-ord-right-01"
        )
        assert right_order.json()["is_correct"] is True
        incomplete = await _answer(
            client, quiz["id"], str(ordering.id), ["A", "B"], "t16-ord-short-01"
        )
        # a structurally invalid submission is rejected before any limit check
        assert incomplete.status_code == 422
        third = await _answer(
            client, quiz["id"], str(ordering.id), ["C", "B", "A"], "t16-ord-third-01"
        )
        assert third.status_code == 409  # valid third attempt → attempt limit
        await content_session.commit()


@pytest.mark.asyncio
async def test_attempt_and_hint_limits_with_replay(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [
            _single_choice("s1", material.objectives[0], refs),
            _single_choice("s2", material.objectives[0], refs),
            _ordering("s3", material.objectives[0], refs),
        ],
    )
    await _junior(settings, "t16.student.limits")

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.limits", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, chapter.chapter_id)
        await content_session.commit()
        question = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )

        first_hint = await _hint(client, quiz["id"], str(question.id), 1, "t16-hint-0001")
        assert first_hint.status_code == 200, first_hint.text
        assert first_hint.json()["text"] == "先读题干"
        replay = await _hint(client, quiz["id"], str(question.id), 1, "t16-hint-0001")
        assert replay.json()["idempotent_replay"] is True
        assert replay.json()["hints_used"] == 1
        out_of_order = await _hint(client, quiz["id"], str(question.id), 3, "t16-hint-0002")
        assert out_of_order.status_code == 409
        conflict = await _hint(client, quiz["id"], str(question.id), 2, "t16-hint-0001")
        assert conflict.status_code == 409

        wrong = await _answer(client, quiz["id"], str(question.id), "B", "t16-att-0001")
        assert wrong.status_code == 200 and wrong.json()["is_correct"] is False
        replay_answer = await _answer(client, quiz["id"], str(question.id), "B", "t16-att-0001")
        assert replay_answer.json()["idempotent_replay"] is True
        assert replay_answer.json()["attempts_used"] == 1
        second = await _answer(client, quiz["id"], str(question.id), "A", "t16-att-0002")
        assert second.json()["attempts_used"] == 2
        third = await _answer(client, quiz["id"], str(question.id), "A", "t16-att-0003")
        assert third.status_code == 409
        forged = await client.post(
            f"/api/v1/quiz-sessions/{quiz['id']}/questions/{question.id}/answers",
            json={
                "answer": "A",
                "idempotency_key": "t16-forged-0001",
                "is_correct": True,
                "score": 100,
            },
            headers=await csrf_headers(client),
        )
        assert forged.status_code == 422

    await content_session.commit()
    attempts = (
        await content_session.scalars(
            select(QuizAttempt).where(QuizAttempt.question_id == question.id)
        )
    ).all()
    assert len(attempts) == 2
    assert [row.attempt_no for row in attempts] == [1, 2]
    hints = (
        await content_session.scalars(
            select(QuizHintEvent).where(QuizHintEvent.question_id == question.id)
        )
    ).all()
    assert len(hints) == 1
    answered_evidence = int(
        await content_session.scalar(
            select(func.count())
            .select_from(QuizEvidence)
            .where(QuizEvidence.kind == "QUIZ_ANSWERED")
        )
        or 0
    )
    assert answered_evidence == 2  # replay added no event
    hint_evidence = int(
        await content_session.scalar(
            select(func.count())
            .select_from(QuizEvidence)
            .where(QuizEvidence.kind == "QUIZ_HINT_VIEWED")
        )
        or 0
    )
    assert hint_evidence == 1


@pytest.mark.asyncio
async def test_hint_limit_is_configurable(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings, quiz_max_hints_per_question=1)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [_single_choice("h1", material.objectives[0], refs)],
    )
    await _primary(settings, "t16.student.hintcap")
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.hintcap", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, chapter.chapter_id)
        await content_session.commit()
        question = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )
        assert quiz["max_hints"] == 1
        first_cap_hint = await _hint(client, quiz["id"], str(question.id), 1, "t16-cap-0001")
        assert first_cap_hint.status_code == 200
        over = await _hint(client, quiz["id"], str(question.id), 2, "t16-cap-0002")
        assert over.status_code == 409


@pytest.mark.asyncio
async def test_system_failure_is_not_a_wrong_answer(
    content_session, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [_single_choice("f1", material.objectives[0], refs)],
    )
    await _primary(settings, "t16.student.failure")
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.failure", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, chapter.chapter_id)
        await content_session.commit()
        question = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )

        from app.modules.assessment import quiz_service
        from app.modules.assessment.scoring import ScoringUnavailable

        def broken(snapshot, answer):
            raise ScoringUnavailable("SCORING_UNAVAILABLE")

        monkeypatch.setattr(quiz_service, "score_answer", broken)
        failed = await _answer(client, quiz["id"], str(question.id), "A", "t16-fail-0001")
        assert failed.status_code == 503
        monkeypatch.undo()

        retry = await _answer(client, quiz["id"], str(question.id), "A", "t16-fail-0001")
        assert retry.status_code == 200, retry.text
        assert retry.json()["attempts_used"] == 1
        assert retry.json()["is_correct"] is True
        failure_question_id = question.id

    await content_session.commit()
    rows = (
        await content_session.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.question_id == failure_question_id)
            .order_by(QuizAttempt.created_at)
        )
    ).all()
    assert [row.outcome for row in rows] == ["SYSTEM_FAILURE", "CORRECT"]
    assert rows[0].attempt_no is None and rows[0].is_correct is None
    wrong_evidence = int(
        await content_session.scalar(
            select(func.count())
            .select_from(QuizEvidence)
            .where(QuizEvidence.kind == "QUIZ_ANSWERED", QuizEvidence.outcome == "INCORRECT")
        )
        or 0
    )
    assert wrong_evidence == 0
    session_row = await content_session.scalar(
        select(QuizSession).where(QuizSession.id == uuid.UUID(quiz["id"]))
    )
    assert session_row.status in ("ACTIVE", "COMPLETED")


@pytest.mark.asyncio
async def test_wrong_answer_creates_review_link_and_similar_source(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    objective = material.objectives[0]
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [_single_choice("r1", objective, refs)],
    )
    await _primary(settings, "t16.student.review")
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.review", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, chapter.chapter_id)
        await content_session.commit()
        question = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )
        wrong = await _answer(client, quiz["id"], str(question.id), "B", "t16-rev-0001")
        assert wrong.status_code == 200 and wrong.json()["is_correct"] is False
        review = await client.get(f"/api/v1/quiz-sessions/{quiz['id']}/review")
        assert review.status_code == 200
        body = review.json()
        assert body["thresholds_version"].startswith("k12.quiz.")
        assert body["items"] and body["items"][0]["reason"] == "INCORRECT"
        assert body["items"][0]["effect_verified"] is False
        assert body["items"][0]["objective_id"] == objective
        # no second same-objective draft exists → honest "no similar source"
        assert body["items"][0]["similar_source"]["draft_id"] is None
        assert body["items"][0]["next_action"] == "REVIEW_SOURCE_MATERIAL"

    # a second validated draft with the same objective becomes the similar source
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [_single_choice("r2", objective, refs)],
    )
    await _primary(settings, "t16.student.review2")
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.review2", PASSWORD)).status_code == 200
        quiz2 = await _open_quiz(client, chapter.chapter_id)
        await content_session.commit()
        question2 = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz2["id"]))
        )
        second_wrong = await _answer(client, quiz2["id"], str(question2.id), "B", "t16-rev-0002")
        assert second_wrong.status_code == 200
        review2 = await client.get(f"/api/v1/quiz-sessions/{quiz2['id']}/review")
        item = review2.json()["items"][0]
        assert item["similar_source"]["draft_id"] is not None
        assert item["similar_source"]["label"]
        assert item["next_action"] == "REVIEW_SIMILAR_QUESTION"

    await content_session.commit()
    links = int(await content_session.scalar(select(func.count()).select_from(QuizReviewLink)) or 0)
    assert links == 2
    linked_evidence = int(
        await content_session.scalar(
            select(func.count())
            .select_from(QuizEvidence)
            .where(QuizEvidence.kind == "QUIZ_REVIEW_LINKED")
        )
        or 0
    )
    assert linked_evidence == 2


@pytest.mark.asyncio
async def test_owner_isolation_and_foreign_question_ids(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [_single_choice("iso1", material.objectives[0], refs)],
    )
    await _primary(settings, "t16.student.owner.a")
    await _primary(settings, "t16.student.owner.b")

    client_a = create_app_client(settings)
    client_b = create_app_client(settings)
    async with client_a, client_b:
        assert (await login(client_a, "t16.student.owner.a", PASSWORD)).status_code == 200
        assert (await login(client_b, "t16.student.owner.b", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client_a, chapter.chapter_id)
        await content_session.commit()
        question = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )
        assert (await client_b.get(f"/api/v1/quiz-sessions/{quiz['id']}")).status_code == 404
        assert (
            await _answer(client_b, quiz["id"], str(question.id), "A", "t16-foreign-01")
        ).status_code == 404
        assert (
            await _hint(client_b, quiz["id"], str(question.id), 1, "t16-foreign-02")
        ).status_code == 404
        assert (await client_b.get(f"/api/v1/quiz-sessions/{quiz['id']}/review")).status_code == 404
        # B can create their own session for the same chapter
        own = await _open_quiz(client_b, chapter.chapter_id)
        assert own["id"] != quiz["id"]


@pytest.mark.asyncio
async def test_source_gating_and_snapshot_stability(
    content_session, test_settings: Settings, tmp_path
):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    objective = material.objectives[0]
    await _primary(settings, "t16.student.source")

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.source", PASSWORD)).status_code == 200
        # QA17: no approved/validated source → explicit refusal, no fallback
        empty = await client.post(
            "/api/v1/quiz-sessions",
            json={"chapter_id": str(chapter.chapter_id)},
            headers=await csrf_headers(client),
        )
        assert empty.status_code == 409
        assert "NO_QUESTIONS_AVAILABLE" in empty.json()["error"]["message"]
        await content_session.commit()
        assert (
            int(await content_session.scalar(select(func.count()).select_from(QuizSession)) or 0)
            == 0
        )

    draft, _ = await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [_single_choice("stab", objective, refs, answer="A")],
    )
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.source", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client, chapter.chapter_id)
        await content_session.commit()
        question = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )
        snapshot_answer = question.correct_answer
        snapshot_stem = question.stem

        # the library row may move on; the quiz snapshot must not
        draft_row = await content_session.scalar(select(QuizDraft).where(QuizDraft.id == draft.id))
        mutated = copy.deepcopy(draft_row.draft)
        mutated["questions"][0]["correct_answer"] = "B"
        mutated["questions"][0]["stem"] = "题库已更新的新题干"
        draft_row.draft = mutated
        draft_row.difficulty = "HARD"
        await content_session.commit()

        still_right = await _answer(client, quiz["id"], str(question.id), "A", "t16-stab-0001")
        assert still_right.status_code == 200
        assert still_right.json()["is_correct"] is True

        await content_session.commit()
        question_after = await content_session.scalar(
            select(QuizQuestion)
            .where(QuizQuestion.id == question.id)
            .execution_options(populate_existing=True)
        )
        assert question_after.correct_answer == snapshot_answer
        assert question_after.stem == snapshot_stem

        # the immutable trigger refuses direct edits of a snapshot row
        with pytest.raises(Exception) as error:
            await content_session.execute(
                text("UPDATE assessment_quiz_questions SET stem = 'hacked' WHERE id = :id"),
                {"id": question.id},
            )
        assert "immutable" in str(error.value)
        await content_session.rollback()  # the failed UPDATE aborted the transaction


@pytest.mark.asyncio
async def test_last_question_concurrency_completes_once(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [
            _single_choice("last1", material.objectives[0], refs),
            _single_choice("last2", material.objectives[0], refs),
            _ordering("last3", material.objectives[0], refs),
        ],
    )
    await _junior(settings, "t16.student.race")
    client_a = create_app_client(settings)
    client_b = create_app_client(settings)
    async with client_a, client_b:
        assert (await login(client_a, "t16.student.race", PASSWORD)).status_code == 200
        assert (await login(client_b, "t16.student.race", PASSWORD)).status_code == 200
        quiz = await _open_quiz(client_a, chapter.chapter_id)
        await content_session.commit()
        questions = (
            await content_session.scalars(
                select(QuizQuestion)
                .where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
                .order_by(QuizQuestion.position)
            )
        ).all()
        for index, (answer, key) in enumerate((("A", "t16-race-0001"), ("A", "t16-race-0002"))):
            setup = await _answer(client_a, quiz["id"], str(questions[index].id), answer, key)
            assert setup.status_code == 200
        last_question_id = questions[2].id
        left, right = await asyncio.gather(
            _answer(
                client_a,
                quiz["id"],
                str(last_question_id),
                ["A", "B", "C"],
                "t16-race-0003",
            ),
            _answer(
                client_b,
                quiz["id"],
                str(last_question_id),
                ["B", "A", "C"],
                "t16-race-0004",
            ),
        )
        assert {left.status_code, right.status_code} <= {200, 409}
        successes = [response for response in (left, right) if response.status_code == 200]
        assert successes, (left.status_code, right.status_code)

    await content_session.commit()
    session_row = await content_session.scalar(
        select(QuizSession)
        .where(QuizSession.id == uuid.UUID(quiz["id"]))
        .execution_options(populate_existing=True)
    )
    assert session_row.status == "COMPLETED"
    assert session_row.completed_at is not None
    completions = int(
        await content_session.scalar(
            select(func.count())
            .select_from(QuizEvidence)
            .where(QuizEvidence.kind == "QUIZ_SESSION_COMPLETED")
        )
        or 0
    )
    assert completions == 1

    attempts_on_last = int(
        await content_session.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(QuizAttempt.question_id == last_question_id)
        )
        or 0
    )
    assert attempts_on_last == len(successes)

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t16.student.race", PASSWORD)).status_code == 200
        after = await _answer(client, quiz["id"], str(last_question_id), "A", "t16-race-0005")
        assert after.status_code == 409


@pytest.mark.asyncio
async def test_dto_question_id_drives_answer_hint_and_rejects_others(
    content_session, test_settings: Settings
):
    """T16 attempt 2 repair regression: the student DTO must expose the id the
    answer/hint routes accept, without leaking answer fields before an attempt,
    and that id must stay owner-scoped."""

    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    material = await load_chapter_material(content_session, chapter_id=chapter.chapter_id)
    refs = _source_refs(material)
    await _auto_validated_draft(
        content_session,
        settings,
        chapter.chapter_id,
        [_single_choice("dtoid1", material.objectives[0], refs)],
    )
    await _primary(settings, "t16.repair.owner")
    await _primary(settings, "t16.repair.other")

    owner_client = create_app_client(settings)
    other_client = create_app_client(settings)
    async with owner_client, other_client:
        assert (await login(owner_client, "t16.repair.owner", PASSWORD)).status_code == 200
        assert (await login(other_client, "t16.repair.other", PASSWORD)).status_code == 200
        quiz = await _open_quiz(owner_client, chapter.chapter_id)
        wire = json.dumps(quiz, ensure_ascii=False)
        assert "correct_answer" not in wire and "explanation" not in wire
        question = quiz["questions"][0]
        assert "id" in question and "question_key" in question
        question_id = uuid.UUID(question["id"])  # a real UUID, not a key
        assert question["question_key"] == "dtoid1"

        await content_session.commit()
        row = await content_session.scalar(
            select(QuizQuestion).where(QuizQuestion.session_id == uuid.UUID(quiz["id"]))
        )
        assert row is not None and row.id == question_id  # DTO id == snapshot row id

        # hint first: a one-question quiz completes on its first answer, after
        # which the session is deliberately read-only.
        hinted = await _hint(owner_client, quiz["id"], question["id"], 1, "t16r-hint-0001")
        assert hinted.status_code == 200, hinted.text
        assert hinted.json()["text"]

        answered = await _answer(owner_client, quiz["id"], question["id"], "A", "t16r-answer-0001")
        assert answered.status_code == 200, answered.text
        assert answered.json()["is_correct"] is True

        # the id is stable across a refresh and now releases the feedback
        refreshed = await owner_client.get(f"/api/v1/quiz-sessions/{quiz['id']}")
        refreshed_question = refreshed.json()["questions"][0]
        assert refreshed_question["id"] == question["id"]
        assert refreshed_question["feedback"]["is_correct"] is True

        # another student cannot use the same session/question id
        assert (await other_client.get(f"/api/v1/quiz-sessions/{quiz['id']}")).status_code == 404
        foreign_answer = await _answer(
            other_client, quiz["id"], question["id"], "A", "t16r-foreign-0001"
        )
        assert foreign_answer.status_code == 404
        foreign_hint = await _hint(other_client, quiz["id"], question["id"], 1, "t16r-foreign-0002")
        assert foreign_hint.status_code == 404

    await content_session.commit()
    assert (
        int(
            await content_session.scalar(
                select(func.count())
                .select_from(QuizAttempt)
                .where(QuizAttempt.question_id == question_id)
            )
            or 0
        )
        == 1
    )
