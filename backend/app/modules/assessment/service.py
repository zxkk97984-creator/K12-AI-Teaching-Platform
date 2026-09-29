"""QUIZ_DRAFT orchestration (T15).

Discipline mirrors T12: a short transaction creates the Designer session and
the generation job, the gateway is then called *outside* that transaction, and
a second short transaction writes the validated draft. A gateway failure or a
rule failure never becomes an approved draft and never substitutes unrelated
questions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.integrations.knodo.gateway import AgentGateway
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import GatewayStatus
from app.modules.assessment.errors import (
    AssessmentError,
    DesignerRequestInvalid,
    HumanApprovalNotAllowed,
    QuizDraftRejected,
)
from app.modules.assessment.models import DesignerSession, GenerationJob, QuizDraft
from app.modules.assessment.specs import (
    build_designer_request,
    conversation_material,
    load_chapter_material,
    load_chapter_material_revision,
    load_designer_fixture_allowance,
)
from app.modules.assessment.validation import (
    CODE_FAKE_REVIEW_FIELD,
    CODE_MULTIPLE_OBJECTS,
    CODE_SCHEMA_INVALID,
    CODE_UNKNOWN_FIELD,
    validate_quiz_draft,
)
from app.modules.identity.models import LearnerProfile, User, UserRole

HARD_REJECT_CODES = frozenset(
    {CODE_SCHEMA_INVALID, CODE_UNKNOWN_FIELD, CODE_MULTIPLE_OBJECTS, CODE_FAKE_REVIEW_FIELD}
)


@dataclass(frozen=True)
class GenerationOutcome:
    job: GenerationJob
    draft: QuizDraft | None


def _request_hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    idempotency_key: str | None = None,
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
        purpose="ADMIN",
        request_id=request_id,
        request_hash=_request_hash(request),
        request_config={"chapter_revision_id": str(material.revision_id)},
        idempotency_key=idempotency_key,
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


async def enqueue_student_generation(
    db: AsyncSession,
    *,
    settings: Settings,
    requester: User,
    chapter_id: uuid.UUID,
    revision_id: uuid.UUID | None = None,
    idempotency_key: str,
    question_count: int | None = None,
    difficulty: str | None = None,
    question_types: list[str] | None = None,
    objective_ids: list[str] | None = None,
    knowledge_point_ids: list[str] | None = None,
    coding_task_refs: list[dict | str] | None = None,
) -> GenerationJob:
    """Persist one owner-scoped student request without calling Knodo.

    The request configuration and exact chapter revision become the worker's
    source of truth. This keeps retries and page refreshes from creating a new
    paid request or switching to a newer chapter revision.
    """

    material = (
        await load_chapter_material_revision(db, revision_id=revision_id)
        if revision_id is not None
        else await load_chapter_material(db, chapter_id=chapter_id)
    )
    request_config = {
        "chapter_id": str(material.chapter_id),
        "chapter_revision_id": str(material.revision_id),
        "chapter_revision": material.revision_number,
        "question_count": question_count,
        "difficulty": difficulty,
        "question_types": list(question_types or []),
        "objective_ids": list(objective_ids or []),
        "knowledge_point_ids": list(knowledge_point_ids or []),
        "coding_task_refs": list(coding_task_refs or []),
    }
    request_hash = _request_hash(request_config)
    existing = await db.scalar(
        select(GenerationJob).where(
            GenerationJob.owner_user_id == requester.id,
            GenerationJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("同一幂等键对应不同的出题配置") from None
        return existing
    request_id = f"student-quiz-{uuid.uuid4().hex[:20]}"
    request_config["request_id"] = request_id
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
        purpose="STUDENT",
        request_id=request_id,
        request_hash=request_hash,
        request_config=request_config,
        idempotency_key=idempotency_key,
        status="QUEUED",
        gateway_mode=settings.gateway_mode,
        fixture=settings.gateway_mode == "fixture",
        request_summary={
            "request_id": request_id,
            "count": question_count,
            "difficulty": difficulty,
            "question_types": list(question_types or []),
            "objective_ids": list(objective_ids or []),
            "knowledge_point_ids": list(knowledge_point_ids or []),
            "coding_task_refs": list(coding_task_refs or []),
            "chapter_revision": material.revision_number,
        },
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(GenerationJob).where(
                GenerationJob.owner_user_id == requester.id,
                GenerationJob.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            raise ValueError("同一幂等键对应不同的出题配置") from None
        return existing
    await db.refresh(job)
    return job


async def enqueue_conversation_generation(
    db: AsyncSession,
    *,
    settings: Settings,
    requester: User,
    snapshot: dict,
    idempotency_key: str,
    question_count: int | None = None,
    difficulty: str | None = None,
    question_types: list[str] | None = None,
) -> GenerationJob:
    """Queue a Designer request grounded in one saved, validated Tutor reply."""
    material = conversation_material(snapshot)
    request_config = {
        "source_kind": "CONVERSATION",
        "source_snapshot": snapshot,
        "question_count": question_count,
        "difficulty": difficulty,
        "question_types": list(question_types or []),
    }
    request_hash = _request_hash(request_config)
    existing = await db.scalar(
        select(GenerationJob).where(
            GenerationJob.owner_user_id == requester.id,
            GenerationJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("同一幂等键对应不同的出题配置")
        return existing
    request_id = f"student-quiz-{uuid.uuid4().hex[:20]}"
    request_config["request_id"] = request_id
    conversation_id = uuid.UUID(snapshot["conversation_id"])
    message_id = uuid.UUID(snapshot["message_id"])
    designer_session = DesignerSession(
        owner_user_id=requester.id,
        chapter_id=None,
        revision_id=None,
        source_conversation_id=conversation_id,
        curriculum_revision=material.curriculum_revision,
        stage=material.stage,
    )
    db.add(designer_session)
    await db.flush()
    job = GenerationJob(
        owner_user_id=requester.id,
        designer_session_id=designer_session.id,
        chapter_id=None,
        revision_id=None,
        source_conversation_id=conversation_id,
        source_message_id=message_id,
        operation=Operation.QUIZ_DRAFT.value,
        purpose="STUDENT",
        request_id=request_id,
        request_hash=request_hash,
        request_config=request_config,
        idempotency_key=idempotency_key,
        status="QUEUED",
        gateway_mode=settings.gateway_mode,
        fixture=settings.gateway_mode == "fixture",
        request_summary={
            "source_kind": "CONVERSATION",
            "source_conversation_id": str(conversation_id),
            "source_message_id": str(message_id),
            "topic": snapshot["topic"],
            "count": question_count,
            "difficulty": difficulty,
            "question_types": list(question_types or []),
        },
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(GenerationJob).where(
                GenerationJob.owner_user_id == requester.id,
                GenerationJob.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            raise ValueError("同一幂等键对应不同的出题配置") from None
        return existing
    await db.refresh(job)
    return job


async def claim_student_generation(
    db: AsyncSession, *, job_id: uuid.UUID, lease_seconds: int = 120
) -> str | None:
    """Atomically claim a queued generation job and return its lease token."""

    job = await db.scalar(
        select(GenerationJob)
        .where(GenerationJob.id == job_id, GenerationJob.purpose == "STUDENT")
        .with_for_update(skip_locked=True)
    )
    if job is None or job.status != "QUEUED":
        return None
    token = uuid.uuid4().hex
    job.status = "RUNNING"
    job.lease_token = token
    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
    await db.commit()
    return token


async def recover_student_generations(db: AsyncSession, *, lease_seconds: int = 120) -> int:
    """Fail closed on worker restarts; never silently re-call a paid request."""

    cutoff = datetime.now(UTC)
    rows = list(
        await db.scalars(
            select(GenerationJob).where(
                GenerationJob.purpose == "STUDENT",
                GenerationJob.status == "RUNNING",
                GenerationJob.lease_expires_at.is_not(None),
                GenerationJob.lease_expires_at < cutoff,
            )
        )
    )
    for job in rows:
        job.status = "FAILED"
        job.error_code = "STUDENT_GENERATION_WORKER_RESTARTED"
        job.error_detail = "任务执行租约已过期，未自动重复调用上游。"
        job.lease_token = None
    await db.commit()
    return len(rows)


async def execute_student_generation(
    settings: Settings, gateway: AgentGateway, job_id: uuid.UUID
) -> str:
    """Consume one queued student generation job using its exact revision."""

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import get_engine

    factory = async_sessionmaker(
        get_engine(settings.active_database_url, settings.app_env), expire_on_commit=False
    )
    async with factory() as db:
        token = await claim_student_generation(
            db, job_id=job_id, lease_seconds=settings.authoring_lease_seconds
        )
        if token is None:
            return "NO_ATTEMPT"
        job = await db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        requester = await db.scalar(select(User).where(User.id == job.owner_user_id))
        config = dict(job.request_config or {})
        material = (
            conversation_material(config["source_snapshot"])
            if config.get("source_kind") == "CONVERSATION"
            else await load_chapter_material_revision(db, revision_id=job.revision_id)
        )
        request_id = str(config.get("request_id") or job.request_id or f"student-quiz-{job.id}")
        allowance = (
            load_designer_fixture_allowance()
            if settings.gateway_mode == "fixture" and material.release_is_test_fixture
            else None
        )
        request, expectation = build_designer_request(
            material,
            request_id=request_id,
            allowance=allowance,
            question_count=config.get("question_count"),
            difficulty=config.get("difficulty"),
            question_types=config.get("question_types") or None,
            objective_ids=config.get("objective_ids") or None,
        )
        if requester is None:
            job.status = "FAILED"
            job.error_code = "OWNER_NOT_FOUND"
            await db.commit()
            return "FAILED"

    try:
        result = await gateway.invoke(Operation.QUIZ_DRAFT, request)
    except Exception:
        result = None

    async with factory() as db:
        job = await db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        if job is None or job.status != "RUNNING" or job.lease_token != token:
            return "STALE"
        if result is None or result.status is not GatewayStatus.OK or result.output is None:
            job.status = "FAILED"
            job.error_code = (
                result.error.reason_code
                if result and result.error is not None
                else "GATEWAY_FAILED"
            )
            job.error_detail = (
                result.error.message if result and result.error is not None else "上游请求失败"
            )
            job.lease_token = None
            await db.commit()
            return "FAILED"
        job.gateway_invocation_id = result.invocation_id
        job.usage = result.usage.model_dump(mode="json")
        try:
            validated = validate_quiz_draft(result.output, expectation=expectation)
        except QuizDraftRejected as exc:
            job.status = "REJECTED"
            job.error_code = exc.code
            job.error_detail = exc.detail
            job.lease_token = None
            await db.commit()
            return "REJECTED"
        draft = QuizDraft(
            job_id=job.id,
            owner_user_id=job.owner_user_id,
            chapter_id=job.chapter_id,
            revision_id=job.revision_id,
            source_conversation_id=job.source_conversation_id,
            curriculum_revision=material.curriculum_revision,
            stage=material.stage,
            request_id=request_id,
            status="AUTO_VALIDATED",
            origin=_origin(settings),
            difficulty=expectation.difficulty,
            question_count=validated.count,
            question_types=[question["type"] for question in validated.questions],
            validation_passed=True,
            validation={"passed": True, "checks": ["SCHEMA", "SOURCE_WHITELIST"]},
            draft=validated.payload,
            student_projection=validated.student_projection,
        )
        db.add(draft)
        await db.flush()
        # Materialize exactly this validated private draft. The helper checks
        # owner and revision, so a newer chapter or another student's draft
        # cannot be selected as a side effect of the worker.
        profile = await db.scalar(
            select(LearnerProfile).where(LearnerProfile.user_id == job.owner_user_id)
        )
        if profile is None:
            job.status = "FAILED"
            job.error_code = "STAGE_REQUIRED"
            job.error_detail = "学生档案不存在，不能创建练习。"
        else:
            from app.modules.assessment.quiz_service import create_quiz_session

            try:
                quiz = await create_quiz_session(
                    db,
                    settings=settings,
                    requester=requester,
                    profile=profile,
                    chapter_id=job.chapter_id,
                    draft_id=draft.id,
                    revision_id=job.revision_id,
                    source_conversation_id=job.source_conversation_id,
                    source_message_id=job.source_message_id,
                    source_title=config.get("source_snapshot", {}).get("topic", ""),
                    code_task_ref=(config.get("coding_task_refs") or [None])[0],
                    commit=False,
                )
            except AssessmentError as exc:
                job.status = "REJECTED"
                job.error_code = exc.code
                job.error_detail = exc.detail
            else:
                job.quiz_session_id = quiz.id
        if job.status == "RUNNING":
            job.status = "SUCCEEDED"
        job.lease_token = None
        await db.commit()
        return job.status


async def list_jobs(
    db: AsyncSession,
    *,
    requester: User,
    limit: int = 20,
    purpose: str | None = None,
    source_conversation_id: uuid.UUID | None = None,
) -> list[GenerationJob]:
    statement = select(GenerationJob).where(GenerationJob.owner_user_id == requester.id)
    if purpose is not None:
        statement = statement.where(GenerationJob.purpose == purpose)
    if source_conversation_id is not None:
        statement = statement.where(GenerationJob.source_conversation_id == source_conversation_id)
    rows = await db.scalars(statement.order_by(GenerationJob.created_at.desc()).limit(limit))
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
    "enqueue_student_generation",
    "claim_student_generation",
    "recover_student_generations",
    "execute_student_generation",
    "get_draft",
    "human_approve",
    "list_jobs",
]
