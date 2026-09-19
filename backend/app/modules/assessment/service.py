"""QUIZ_DRAFT orchestration (T15).

Discipline mirrors T12: a short transaction creates the Designer session and
the generation job, the gateway is then called *outside* that transaction, and
a second short transaction writes the validated draft. A gateway failure or a
rule failure never becomes an approved draft and never substitutes unrelated
questions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.integrations.knodo.gateway import AgentGateway
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import GatewayStatus
from app.modules.assessment.errors import (
    DesignerRequestInvalid,
    HumanApprovalNotAllowed,
    QuizDraftRejected,
)
from app.modules.assessment.models import DesignerSession, GenerationJob, QuizDraft
from app.modules.assessment.specs import (
    build_designer_request,
    load_chapter_material,
    load_designer_fixture_allowance,
)
from app.modules.assessment.validation import (
    CODE_FAKE_REVIEW_FIELD,
    CODE_MULTIPLE_OBJECTS,
    CODE_SCHEMA_INVALID,
    CODE_UNKNOWN_FIELD,
    validate_quiz_draft,
)
from app.modules.identity.models import User, UserRole

HARD_REJECT_CODES = frozenset(
    {CODE_SCHEMA_INVALID, CODE_UNKNOWN_FIELD, CODE_MULTIPLE_OBJECTS, CODE_FAKE_REVIEW_FIELD}
)


@dataclass(frozen=True)
class GenerationOutcome:
    job: GenerationJob
    draft: QuizDraft | None


def _origin(settings: Settings) -> str:
    # Fixture output is never labelled as a model draft (no false provenance).
    return "FIXTURE" if settings.gateway_mode == "fixture" else "MODEL_DRAFT"


async def create_quiz_draft_job(
    db: AsyncSession,
    *,
    settings: Settings,
    gateway: AgentGateway,
    requester: User,
    chapter_id: uuid.UUID,
) -> GenerationOutcome:
    material = await load_chapter_material(db, chapter_id=chapter_id)
    allowance = None
    if settings.gateway_mode == "fixture" and material.release_is_test_fixture:
        allowance = load_designer_fixture_allowance()

    request_id = f"quiz-{uuid.uuid4().hex[:20]}"
    request, expectation = build_designer_request(
        material, request_id=request_id, allowance=allowance
    )

    designer_session = DesignerSession(
        owner_user_id=requester.id,
        chapter_id=material.chapter_id,
        revision_id=material.revision_id,
        curriculum_revision=material.curriculum_revision,
        stage=material.stage,
    )
    db.add(designer_session)
    await db.flush()
    job = GenerationJob(
        owner_user_id=requester.id,
        designer_session_id=designer_session.id,
        chapter_id=material.chapter_id,
        revision_id=material.revision_id,
        operation=Operation.QUIZ_DRAFT.value,
        status="RUNNING",
        gateway_mode=settings.gateway_mode,
        fixture=settings.gateway_mode == "fixture",
        fixture_allowance=allowance,
        request_summary={
            "request_id": request_id,
            "count": expectation.count,
            "difficulty": expectation.difficulty,
            "question_types": list(expectation.question_types),
            "objective_count": len(expectation.objective_ids),
            "source_count": len(expectation.sources),
        },
    )
    db.add(job)
    # Short transaction: the gateway call happens after this commit.
    await db.commit()
    await db.refresh(job)

    result = await gateway.invoke(Operation.QUIZ_DRAFT, request)
    job.gateway_invocation_id = result.invocation_id
    job.usage = result.usage.model_dump(mode="json")

    if result.status is not GatewayStatus.OK or result.output is None:
        job.status = "FAILED"
        job.error_code = (
            result.error.reason_code if result.error is not None else result.status.value
        )
        job.error_detail = result.error.message if result.error is not None else "无可用题稿"
        await db.commit()
        return GenerationOutcome(job=job, draft=None)

    try:
        validated = validate_quiz_draft(result.output, expectation=expectation)
    except QuizDraftRejected as exc:
        job.status = "REJECTED"
        job.error_code = exc.code
        job.error_detail = exc.detail
        draft = None
        if exc.code not in HARD_REJECT_CODES:
            # Format-valid but rule-failing: keep an audit draft without the
            # unusable payload and without any student projection.
            draft = QuizDraft(
                job_id=job.id,
                owner_user_id=requester.id,
                chapter_id=material.chapter_id,
                revision_id=material.revision_id,
                curriculum_revision=material.curriculum_revision,
                stage=material.stage,
                request_id=request_id,
                status="DRAFT",
                origin=_origin(settings),
                difficulty=str(result.output.get("difficulty") or expectation.difficulty)[:16],
                question_count=len(result.output.get("questions") or []) or 1,
                question_types=[
                    question.get("type")
                    for question in (result.output.get("questions") or [])
                    if isinstance(question, dict)
                ],
                validation_passed=False,
                validation={"passed": False, "code": exc.code, "detail": exc.detail},
                draft=None,
                student_projection=None,
            )
            db.add(draft)
        await db.commit()
        if draft is not None:
            await db.refresh(draft)
        return GenerationOutcome(job=job, draft=draft)

    draft = QuizDraft(
        job_id=job.id,
        owner_user_id=requester.id,
        chapter_id=material.chapter_id,
        revision_id=material.revision_id,
        curriculum_revision=material.curriculum_revision,
        stage=material.stage,
        request_id=request_id,
        status="AUTO_VALIDATED",
        origin=_origin(settings),
        difficulty=expectation.difficulty,
        question_count=validated.count,
        question_types=[question["type"] for question in validated.questions],
        validation_passed=True,
        validation={
            "passed": True,
            "code": None,
            "checks": [
                "SCHEMA",
                "ECHO",
                "COUNT",
                "DIFFICULTY",
                "TYPE",
                "ANSWER_IN_OPTIONS",
                "ORDERING_PERMUTATION",
                "SOURCE_WHITELIST",
                "OBJECTIVE_WHITELIST",
                "NO_FAKE_REVIEW_FIELDS",
            ],
        },
        draft=validated.payload,
        student_projection=validated.student_projection,
    )
    db.add(draft)
    job.status = "SUCCEEDED"
    await db.commit()
    await db.refresh(draft)
    return GenerationOutcome(job=job, draft=draft)


async def list_jobs(db: AsyncSession, *, requester: User, limit: int = 20) -> list[GenerationJob]:
    rows = await db.scalars(
        select(GenerationJob)
        .where(GenerationJob.owner_user_id == requester.id)
        .order_by(GenerationJob.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def get_draft(db: AsyncSession, *, requester: User, draft_id: uuid.UUID) -> QuizDraft | None:
    return await db.scalar(
        select(QuizDraft).where(QuizDraft.id == draft_id, QuizDraft.owner_user_id == requester.id)
    )


async def human_approve(
    db: AsyncSession, *, draft_id: uuid.UUID, reviewer: User, note: str | None = None
) -> QuizDraft:
    """HUMAN_APPROVED is written only here, by a real human admin subject.

    This function is deliberately not exposed by any HTTP route in T15: the
    review workflow lands with the teacher tooling, and the model path can
    never reach it.
    """

    if reviewer.role != UserRole.ADMIN:
        raise HumanApprovalNotAllowed("只有管理员/教研人员可以人工审校")
    draft = await db.scalar(select(QuizDraft).where(QuizDraft.id == draft_id))
    if draft is None:
        raise HumanApprovalNotAllowed("题稿不存在")
    if draft.status != "AUTO_VALIDATED" or not draft.validation_passed:
        raise HumanApprovalNotAllowed("只有通过确定性校验的题稿才能人工通过")
    draft.status = "HUMAN_APPROVED"
    draft.review_subject_id = reviewer.id
    draft.reviewed_at = datetime.now(UTC)
    draft.review_note = note
    await db.commit()
    await db.refresh(draft)
    return draft


__all__ = [
    "DesignerRequestInvalid",
    "GenerationOutcome",
    "create_quiz_draft_job",
    "get_draft",
    "human_approve",
    "list_jobs",
]
