"""Student quiz API (T16). The practice UI itself ships with T17."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.assessment.dto import job_public as _job_public
from app.modules.assessment.errors import AssessmentError
from app.modules.assessment.models import (
    GenerationJob,
    QuizAnswerDraft,
    QuizAttempt,
    QuizHintEvent,
    QuizQuestion,
    QuizSession,
)
from app.modules.assessment.quiz_dto import session_public
from app.modules.assessment.quiz_service import (
    QuizRequestRejected,
    QuizSourceUnavailable,
    create_quiz_session,
    get_question,
    request_hint,
    review_overview,
    session_snapshot,
    submit_answer,
)
from app.modules.assessment.quiz_service import (
    get_session as get_quiz_session,
)
from app.modules.assessment.service import (
    enqueue_conversation_generation,
    enqueue_student_generation,
    list_jobs,
)
from app.modules.codelab.models import CodeRun, CodeTaskRevision
from app.modules.content.models import Chapter, Course
from app.modules.content.service import viewer_scope_from_profile, visible_chapter_detail
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.identity.models import LearnerProfile
from app.modules.learning.policy import build_policy
from app.modules.teaching.models import ConversationMessage, LessonSession

router = APIRouter(tags=["assessment"])


@router.get("/quiz-wrong-questions")
async def wrong_questions(
    subject: str | None = Query(default=None, max_length=80),
    knowledge_point: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=100, ge=1, le=200),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Historical wrong attempts from trusted quiz scoring only."""
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="请先设置学段")
    statement = (
        select(QuizAttempt, QuizQuestion, QuizSession, Course.topic)
        .join(QuizQuestion, QuizQuestion.id == QuizAttempt.question_id)
        .join(QuizSession, QuizSession.id == QuizAttempt.session_id)
        .outerjoin(Chapter, Chapter.id == QuizSession.chapter_id)
        .outerjoin(Course, Course.id == Chapter.course_id)
        .where(
            QuizAttempt.owner_user_id == context.user.id,
            QuizSession.owner_user_id == context.user.id,
            QuizSession.stage == profile.stage,
            QuizAttempt.outcome == "INCORRECT",
        )
        .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc())
        .limit(limit * 5)
    )
    rows = (await db.execute(statement)).all()
    results: list[dict[str, Any]] = []
    seen: set[uuid.UUID] = set()
    for attempt, question, session, course_topic in rows:
        if question.id in seen:
            continue
        topic = course_topic or "综合"
        if subject and topic != subject:
            continue
        points = list(session.knowledge_point_slugs or [])
        if knowledge_point and knowledge_point not in points:
            continue
        seen.add(question.id)
        hints = list(
            await db.scalars(
                select(QuizHintEvent.level).where(
                    QuizHintEvent.owner_user_id == context.user.id,
                    QuizHintEvent.session_id == session.id,
                    QuizHintEvent.question_id == question.id,
                )
            )
        )
        results.append(
            {
                "question_id": str(question.id),
                "session_id": str(session.id),
                "source_conversation_id": str(session.source_conversation_id)
                if session.source_conversation_id
                else None,
                "source_title": session.source_title,
                "subject": topic,
                "knowledge_points": points,
                "type": question.type,
                "stem": question.stem,
                "student_answer": attempt.answer,
                "outcome": attempt.outcome,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
                "hints_used": len(hints),
                "released_hints": [
                    question.hints[level - 1]
                    for level in sorted(hints)
                    if 0 < level <= len(question.hints)
                ],
                "attempted_at": attempt.created_at.isoformat(),
            }
        )
        if len(results) >= limit:
            break
    return {"items": results, "total": len(results), "stage": profile.stage}


_IDEMPOTENCY_PATTERN = r"^[A-Za-z0-9._:-]{8,64}$"


class QuizSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: uuid.UUID


class AnswerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Any = Field(description="选项 key / 布尔值 / 排序 key 数组")
    idempotency_key: str = Field(pattern=_IDEMPOTENCY_PATTERN)


class HintCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=1, le=3)
    idempotency_key: str = Field(pattern=_IDEMPOTENCY_PATTERN)


class RepeatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)


class StudentGenerationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    knowledge_point: str | None = Field(default=None, min_length=2, max_length=160)
    chapter_revision: int | None = Field(default=None, ge=1)
    knowledge_point_ids: list[str] | None = None
    idempotency_key: str = Field(pattern=_IDEMPOTENCY_PATTERN)
    ordinary_question_count: int | None = Field(default=None, ge=1, le=5)
    ordinary_question_types: list[str] | None = None
    difficulty: str | None = None
    coding_task_refs: list[dict[str, Any] | str] | None = None


class QuizDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Any
    base_revision: int = Field(default=0, ge=0)


class QuizPositionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=0, le=100)


class QuizSummaryProgressDTO(BaseModel):
    answered: int
    correct: int
    total: int


class QuizSessionSummaryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    chapter_id: uuid.UUID | None
    source_conversation_id: uuid.UUID | None = None
    title: str
    status: Literal["ACTIVE", "COMPLETED"]
    progress: QuizSummaryProgressDTO
    has_code: bool
    is_favorite: bool
    created_at: datetime
    completed_at: datetime | None


class QuizSessionSummaryListDTO(BaseModel):
    items: list[QuizSessionSummaryDTO]
    total: int
    limit: int
    offset: int


class QuizSessionFullListDTO(BaseModel):
    items: list[dict[str, Any]]
    total: int


_ERROR_STATUS = {
    "CHAPTER_NOT_VISIBLE": status.HTTP_404_NOT_FOUND,
    "CHAPTER_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "STAGE_REQUIRED": status.HTTP_409_CONFLICT,
    "STAGE_MISMATCH": status.HTTP_409_CONFLICT,
    "NO_QUESTIONS_AVAILABLE": status.HTTP_409_CONFLICT,
    "INVALID_ANSWER": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "SCORING_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _raise(caught: AssessmentError) -> None:
    code = getattr(caught, "code", "QUIZ_REQUEST_REJECTED")
    http_status = _ERROR_STATUS.get(code, status.HTTP_409_CONFLICT)
    raise HTTPException(status_code=http_status, detail=f"{code}: {caught.detail}") from caught


@router.get("/quiz-options")
async def read_quiz_options(
    chapter_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="STAGE_REQUIRED: 请先完成学段设置")
    viewer = viewer_scope_from_profile(profile, request.app.state.settings)
    chapter = await visible_chapter_detail(db, chapter_id=chapter_id, viewer=viewer)
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不可用")
    policy = build_policy(
        stage=profile.stage,
        grade=profile.grade,
        preferred_style=profile.preferred_style,
        evidence_level="NONE",
        proactive_guidance_enabled=profile.proactive_guidance_enabled,
    )
    return {
        "chapter_id": str(chapter_id),
        "chapter_revision": chapter.revision,
        "revision_id": str(chapter.revision_id),
        "knowledge_points": [
            {"id": item.slug, "name": item.name, "topic": item.topic}
            for item in chapter.knowledge_points
        ],
        "stage": profile.stage,
        "allowed_question_types": list(policy.allowed_question_types),
        "allowed_difficulties": list(policy.allowed_difficulties),
        "max_question_count": policy.max_quiz_questions,
        "ai_generation_available": True,
        "notice": "题目将基于当前可访问章节内容生成，并经过服务器结构校验。",
    }


@router.get("/quiz-options/conversation")
async def read_conversation_quiz_options(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="请先选择学段")
    policy = build_policy(
        stage=profile.stage,
        grade=profile.grade,
        preferred_style=profile.preferred_style,
        evidence_level="NONE",
        proactive_guidance_enabled=profile.proactive_guidance_enabled,
    )
    return {
        "stage": profile.stage,
        "max_question_count": policy.max_quiz_questions,
        "allowed_difficulties": list(policy.allowed_difficulties),
        "allowed_question_types": list(policy.allowed_question_types),
    }


@router.post(
    "/quiz-generation-jobs",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_student_generation(
    body: StudentGenerationCreate,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Enqueue a private student generation request.

    Designer is called only by the shared worker. A retry or browser refresh
    therefore observes the same durable job instead of creating a second paid
    request.
    """
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="STAGE_REQUIRED: 请先完成学段设置")
    if body.conversation_id is not None:
        if body.chapter_id is not None or body.message_id is None or not body.knowledge_point:
            raise HTTPException(status_code=422, detail="会话出题需要教师消息和知识点")
        conversation = await db.scalar(
            select(LessonSession).where(
                LessonSession.id == body.conversation_id,
                LessonSession.owner_user_id == context.user.id,
                LessonSession.stage == profile.stage,
            )
        )
        message = await db.scalar(
            select(ConversationMessage).where(
                ConversationMessage.id == body.message_id,
                ConversationMessage.session_id == body.conversation_id,
                ConversationMessage.owner_user_id == context.user.id,
                ConversationMessage.role == "ASSISTANT",
            )
        )
        if conversation is None or message is None or not message.card:
            raise HTTPException(status_code=404, detail="可用于出题的教师回复不存在")
        last_user = await db.scalar(
            select(ConversationMessage)
            .where(
                ConversationMessage.session_id == conversation.id,
                ConversationMessage.owner_user_id == context.user.id,
                ConversationMessage.role == "USER",
                ConversationMessage.created_at <= message.created_at,
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        topic = body.knowledge_point.strip()
        chapter_title = str((conversation.context or {}).get("chapter", {}).get("title") or "")
        if all(
            topic not in text
            for text in (
                message.content_markdown,
                last_user.content_markdown if last_user else "",
                chapter_title if conversation.conversation_type == "LESSON" else "",
            )
        ):
            raise HTTPException(status_code=422, detail="知识点不在这轮教师对话中，请先向老师提问")
        policy = build_policy(
            stage=profile.stage,
            grade=profile.grade,
            preferred_style=profile.preferred_style,
            evidence_level="NONE",
            proactive_guidance_enabled=profile.proactive_guidance_enabled,
        )
        if (
            body.ordinary_question_count
            and body.ordinary_question_count > policy.max_quiz_questions
        ):
            raise HTTPException(status_code=422, detail="题量超过当前学段策略上限")
        if body.difficulty and body.difficulty not in policy.allowed_difficulties:
            raise HTTPException(status_code=422, detail="当前学段不支持该难度")
        if body.ordinary_question_types and set(body.ordinary_question_types) - set(
            policy.allowed_question_types
        ):
            raise HTTPException(status_code=422, detail="包含当前学段不支持的题型")
        if body.coding_task_refs or body.knowledge_point_ids:
            raise HTTPException(status_code=422, detail="会话出题不接受章节或编程题引用")
        snapshot = {
            "conversation_id": str(conversation.id),
            "message_id": str(message.id),
            "stage": profile.stage,
            "topic": topic,
            "text": message.content_markdown[:8000],
            "fixture": request.app.state.settings.gateway_mode == "fixture",
        }
        try:
            job = await enqueue_conversation_generation(
                db,
                settings=request.app.state.settings,
                requester=context.user,
                snapshot=snapshot,
                idempotency_key=body.idempotency_key,
                question_count=body.ordinary_question_count,
                difficulty=body.difficulty,
                question_types=body.ordinary_question_types,
            )
        except ValueError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except IntegrityError:
            await db.rollback()
            job = await db.scalar(
                select(GenerationJob).where(
                    GenerationJob.owner_user_id == context.user.id,
                    GenerationJob.idempotency_key == body.idempotency_key,
                )
            )
            if job is None:
                raise
        if job.status == "QUEUED" and request.app.state.settings.assessment_autorun:
            from app.modules.assessment.service import execute_student_generation

            asyncio.create_task(
                execute_student_generation(
                    request.app.state.settings, request.app.state.gateway, job.id
                )
            )
        return {"job": _job_public(job), "quiz": None}
    if body.chapter_id is None:
        raise HTTPException(status_code=422, detail="请选择章节或教师会话作为出题来源")
    viewer = viewer_scope_from_profile(profile, request.app.state.settings)
    chapter = await visible_chapter_detail(db, chapter_id=body.chapter_id, viewer=viewer)
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不可用")
    if body.chapter_revision is not None and body.chapter_revision != chapter.revision:
        raise HTTPException(status_code=409, detail="章节版本已变化，请重新读取出题选项")
    allowed_knowledge_points = {item.slug for item in chapter.knowledge_points}
    if body.knowledge_point_ids:
        unknown = set(body.knowledge_point_ids) - allowed_knowledge_points
        if unknown:
            raise HTTPException(status_code=422, detail="包含当前章节不可用的知识点")
    coding_task_refs: list[dict[str, Any]] = []
    for raw_ref in body.coding_task_refs or []:
        if isinstance(raw_ref, str):
            parts = raw_ref.split(":", 1)
            ref = {
                "task_id": parts[0],
                "revision": int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0,
            }
        elif isinstance(raw_ref, dict):
            raw_revision = raw_ref.get("revision")
            if (
                not isinstance(raw_revision, int)
                or isinstance(raw_revision, bool)
                or raw_revision < 1
            ):
                raise HTTPException(status_code=422, detail="编程题引用版本无效")
            ref = {"task_id": str(raw_ref.get("task_id") or ""), "revision": raw_revision}
        else:
            raise HTTPException(status_code=422, detail="编程题引用格式无效")
        task = await db.scalar(
            select(CodeTaskRevision).where(
                CodeTaskRevision.task_id == ref["task_id"],
                CodeTaskRevision.revision == ref["revision"],
                CodeTaskRevision.status.in_(("DRAFT", "PUBLISHED")),
            )
        )
        binding = dict(task.chapter_binding or {}) if task else {}
        if task is None or binding.get("stage") != profile.stage:
            raise HTTPException(status_code=422, detail="编程题版本不可用于当前学段")
        coding_task_refs.append(ref)
    policy = build_policy(
        stage=profile.stage,
        grade=profile.grade,
        preferred_style=profile.preferred_style,
        evidence_level="NONE",
        proactive_guidance_enabled=profile.proactive_guidance_enabled,
    )
    if (
        body.ordinary_question_count is not None
        and body.ordinary_question_count > policy.max_quiz_questions
    ):
        raise HTTPException(status_code=422, detail="题量超过当前学段策略上限")
    if body.difficulty is not None and body.difficulty not in policy.allowed_difficulties:
        raise HTTPException(status_code=422, detail="当前学段不支持该难度")
    if body.ordinary_question_types:
        unsupported = set(body.ordinary_question_types) - set(policy.allowed_question_types)
        if unsupported:
            raise HTTPException(status_code=422, detail="包含当前学段不支持的题型")
    try:
        job = await enqueue_student_generation(
            db,
            settings=request.app.state.settings,
            requester=context.user,
            chapter_id=body.chapter_id,
            revision_id=chapter.revision_id,
            idempotency_key=body.idempotency_key,
            question_count=body.ordinary_question_count,
            difficulty=body.difficulty,
            question_types=body.ordinary_question_types,
            knowledge_point_ids=body.knowledge_point_ids,
            coding_task_refs=coding_task_refs,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError:
        await db.rollback()
        existing_job = await db.scalar(
            select(GenerationJob).where(
                GenerationJob.owner_user_id == context.user.id,
                GenerationJob.idempotency_key == body.idempotency_key,
            )
        )
        if existing_job is None:
            raise
        job = existing_job
    if job.status == "QUEUED" and request.app.state.settings.assessment_autorun:
        from app.modules.assessment.service import execute_student_generation

        asyncio.create_task(
            execute_student_generation(
                request.app.state.settings, request.app.state.gateway, job.id
            )
        )
    return {
        "job": {
            "id": str(job.id),
            "status": job.status,
            "error_code": job.error_code,
            "quiz_session_id": str(job.quiz_session_id) if job.quiz_session_id else None,
        },
        "quiz": None,
    }


@router.get("/quiz-generation-jobs")
async def list_student_generation_jobs(
    conversation_id: uuid.UUID | None = None,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    jobs = await list_jobs(
        db,
        requester=context.user,
        purpose="STUDENT",
        source_conversation_id=conversation_id,
        limit=100 if conversation_id is not None else 20,
    )
    return {"items": [_job_public(job) for job in jobs], "total": len(jobs)}


@router.get("/quiz-generation-jobs/{job_id}")
async def read_student_generation_job(
    job_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = await db.scalar(
        select(GenerationJob).where(
            GenerationJob.id == job_id,
            GenerationJob.owner_user_id == context.user.id,
            GenerationJob.purpose == "STUDENT",
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="出题任务不存在")
    return {"job": _job_public(job)}


async def _owned_session(
    db: AsyncSession, *, owner_id: uuid.UUID, session_id: uuid.UUID
) -> QuizSession:
    quiz = await get_quiz_session(db, session_id=session_id, owner_id=owner_id)
    if quiz is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="测验不存在")
    return quiz


async def _owned_question(
    db: AsyncSession, *, session_id: uuid.UUID, question_id: uuid.UUID
) -> QuizQuestion:
    question = await get_question(db, session_id=session_id, question_id=question_id)
    if question is None:
        # Another student's question id (or another session) is simply absent.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题目不存在")
    return question


def _validate_draft_shape(question: QuizQuestion, answer: Any) -> None:
    if question.type == "CODE":
        raise HTTPException(status_code=422, detail="编程题不保存普通答案草稿")
    if question.type == "SINGLE_CHOICE":
        keys = {
            item.get("key")
            for item in (question.options or [])
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        }
        if not isinstance(answer, str) or answer not in keys:
            raise HTTPException(status_code=422, detail="答案必须是选项 key 之一")
        return
    if question.type == "TRUE_FALSE":
        if not isinstance(answer, bool):
            raise HTTPException(status_code=422, detail="判断题答案必须是 JSON 布尔值")
        return
    keys = [
        item.get("key")
        for item in (question.items or [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    ]
    if (
        not isinstance(answer, list)
        or len(answer) != len(keys)
        or any(not isinstance(item, str) for item in answer)
        or set(answer) != set(keys)
        or len(set(answer)) != len(answer)
    ):
        raise HTTPException(status_code=422, detail="排序答案必须是全部排序项的一个排列")


async def _public_with_state(db: AsyncSession, *, quiz: QuizSession) -> dict[str, Any]:
    snapshot = await session_snapshot(db, session=quiz)
    public = session_public(
        quiz,
        questions=snapshot["questions"],
        attempts=snapshot["attempts"],
        hints=snapshot["hints"],
    )
    drafts = list(
        await db.scalars(
            select(QuizAnswerDraft)
            .where(
                QuizAnswerDraft.owner_user_id == quiz.owner_user_id,
                QuizAnswerDraft.session_id == quiz.id,
            )
            .order_by(QuizAnswerDraft.updated_at)
        )
    )
    public["current_position"] = quiz.current_position
    code_rows = await db.execute(
        select(CodeRun.question_id, CodeRun.correctness_status)
        .where(
            CodeRun.owner_user_id == quiz.owner_user_id,
            CodeRun.quiz_session_id == quiz.id,
            CodeRun.purpose == "GRADE",
            CodeRun.status.not_in(
                ("QUEUED", "RUNNING", "CANCELLED", "UNAVAILABLE", "SYSTEM_ERROR")
            ),
            CodeRun.correctness_status.in_(("PASSED", "PARTIAL", "FAILED")),
        )
        .order_by(CodeRun.created_at, CodeRun.id)
    )
    code_question_ids = {
        question.id for question in snapshot["questions"] if question.type == "CODE"
    }
    latest_code = {
        question_id: correctness
        for question_id, correctness in code_rows
        if question_id in code_question_ids
    }
    public["progress"]["answered"] += len(latest_code)
    public["progress"]["correct"] += sum(
        correctness == "PASSED" for correctness in latest_code.values()
    )
    public["drafts"] = {
        str(draft.question_id): {
            "answer": draft.answer,
            "revision": draft.revision,
            "updated_at": draft.updated_at.isoformat(),
        }
        for draft in drafts
    }
    public["last_submitted_answers"] = {
        str(question_id): rows[-1].answer
        for question_id, rows in snapshot["attempts"].items()
        if rows and rows[-1].attempt_no is not None
    }
    return public


@router.post(
    "/quiz-sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def open_quiz_session(
    body: QuizSessionCreate,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    try:
        quiz = await create_quiz_session(
            db,
            settings=request.app.state.settings,
            requester=context.user,
            profile=profile,
            chapter_id=body.chapter_id,
        )
    except QuizSourceUnavailable as caught:
        _raise(caught)
    except QuizRequestRejected as caught:
        _raise(caught)
    return await _public_with_state(db, quiz=quiz)


@router.get("/quiz-sessions/{session_id}")
async def read_quiz_session(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    return await _public_with_state(db, quiz=quiz)


@router.get("/quiz-sessions", response_model=QuizSessionSummaryListDTO | QuizSessionFullListDTO)
async def list_quiz_sessions(
    status_filter: str | None = None,
    favorite_only: bool = False,
    view: Literal["full", "summary"] = "full",
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> QuizSessionSummaryListDTO | dict[str, Any]:
    """List only the current student's durable practice snapshots."""
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="请先选择学段")
    statement = select(QuizSession).where(
        QuizSession.owner_user_id == context.user.id,
        QuizSession.stage == profile.stage,
    )
    if status_filter in {"ACTIVE", "COMPLETED"}:
        statement = statement.where(QuizSession.status == status_filter)
    if favorite_only:
        statement = statement.where(QuizSession.is_favorite.is_(True))
    if view == "summary":
        total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = (
            await db.execute(
                statement.with_only_columns(QuizSession, Chapter.title)
                .outerjoin(Chapter, Chapter.id == QuizSession.chapter_id)
                .order_by(
                    func.coalesce(QuizSession.completed_at, QuizSession.created_at).desc(),
                    QuizSession.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
        session_ids = [quiz.id for quiz, _ in rows]
        attempts: dict[tuple[uuid.UUID, uuid.UUID], bool] = {}
        code_results: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
        has_code: set[uuid.UUID] = set()
        code_question_ids: set[uuid.UUID] = set()
        if session_ids:
            attempt_rows = await db.execute(
                select(
                    QuizAttempt.session_id,
                    QuizAttempt.question_id,
                    QuizAttempt.is_correct,
                )
                .where(
                    QuizAttempt.owner_user_id == context.user.id,
                    QuizAttempt.session_id.in_(session_ids),
                    QuizAttempt.attempt_no.is_not(None),
                )
                .order_by(QuizAttempt.attempt_no)
            )
            for session_id, question_id, is_correct in attempt_rows:
                attempts[(session_id, question_id)] = is_correct is True
            code_rows = await db.execute(
                select(CodeRun.quiz_session_id, CodeRun.question_id, CodeRun.correctness_status)
                .where(
                    CodeRun.owner_user_id == context.user.id,
                    CodeRun.quiz_session_id.in_(session_ids),
                    CodeRun.purpose == "GRADE",
                    CodeRun.status.not_in(
                        ("QUEUED", "RUNNING", "CANCELLED", "UNAVAILABLE", "SYSTEM_ERROR")
                    ),
                    CodeRun.correctness_status.in_(("PASSED", "PARTIAL", "FAILED")),
                )
                .order_by(CodeRun.created_at, CodeRun.id)
            )
            code_results = {
                (session_id, question_id): correctness
                for session_id, question_id, correctness in code_rows
                if question_id is not None
            }
            code_question_rows = await db.execute(
                select(QuizQuestion.session_id, QuizQuestion.id).where(
                    QuizQuestion.session_id.in_(session_ids), QuizQuestion.type == "CODE"
                )
            )
            for session_id, question_id in code_question_rows:
                has_code.add(session_id)
                code_question_ids.add(question_id)
            code_results = {
                key: correctness
                for key, correctness in code_results.items()
                if key[1] in code_question_ids
            }
        return QuizSessionSummaryListDTO(
            items=[
                QuizSessionSummaryDTO(
                    id=quiz.id,
                    chapter_id=quiz.chapter_id,
                    source_conversation_id=quiz.source_conversation_id,
                    title=(
                        f"{chapter_title} · 章节练习"
                        if chapter_title
                        else f"{quiz.source_title} · 趣味练习"
                    ),
                    status=quiz.status,
                    progress=QuizSummaryProgressDTO(
                        answered=sum(1 for session_id, _ in attempts if session_id == quiz.id)
                        + sum(1 for session_id, _ in code_results if session_id == quiz.id),
                        correct=sum(
                            1
                            for (session_id, _), is_correct in attempts.items()
                            if session_id == quiz.id and is_correct
                        )
                        + sum(
                            1
                            for (session_id, _), correctness in code_results.items()
                            if session_id == quiz.id and correctness == "PASSED"
                        ),
                        total=quiz.question_count,
                    ),
                    has_code=quiz.id in has_code,
                    is_favorite=quiz.is_favorite,
                    created_at=quiz.created_at,
                    completed_at=quiz.completed_at,
                )
                for quiz, chapter_title in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
    rows = list(await db.scalars(statement.order_by(QuizSession.created_at.desc()).limit(100)))
    items: list[dict[str, Any]] = []
    for quiz in rows:
        snapshot = await session_snapshot(db, session=quiz)
        public = await _public_with_state(db, quiz=quiz)
        public["title"] = (
            f"章节练习 · {str(quiz.chapter_id)[:8]}"
            if quiz.chapter_id
            else f"{quiz.source_title} · 趣味练习"
        )
        public["has_code"] = any(question.type == "CODE" for question in snapshot["questions"])
        items.append(public)
    return {"items": items, "total": len(items)}


@router.post(
    "/quiz-sessions/{session_id}/repeat",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def repeat_quiz_session(
    session_id: uuid.UUID,
    body: RepeatCreate,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a fresh immutable snapshot from one owned practice session."""
    source = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    if profile is None or source.stage != profile.stage:
        raise HTTPException(status_code=409, detail="请切回练习所属学段再重新练习")
    questions = await session_snapshot(db, session=source)
    new_session = QuizSession(
        owner_user_id=context.user.id,
        chapter_id=source.chapter_id,
        revision_id=source.revision_id,
        source_conversation_id=source.source_conversation_id,
        source_message_id=source.source_message_id,
        source_title=source.source_title,
        draft_id=source.draft_id,
        curriculum_revision=source.curriculum_revision,
        stage=source.stage,
        grade=source.grade,
        source_kind=source.source_kind,
        source_label=source.source_label,
        difficulty=source.difficulty,
        question_count=source.question_count,
        max_attempts=source.max_attempts,
        max_hints=source.max_hints,
        knowledge_point_slugs=list(source.knowledge_point_slugs or []),
        scoring_version=source.scoring_version,
        thresholds_version=source.thresholds_version,
        status="ACTIVE",
        base_revision=0,
    )
    db.add(new_session)
    await db.flush()
    for original in questions["questions"]:
        db.add(
            QuizQuestion(
                session_id=new_session.id,
                position=original.position,
                question_key=original.question_key,
                objective_id=original.objective_id,
                type=original.type,
                stem=original.stem,
                options=original.options,
                items=original.items,
                correct_answer=original.correct_answer,
                explanation=original.explanation,
                hints=list(original.hints or []),
                source_refs=list(original.source_refs or []),
                origin=original.origin,
                source_draft_id=original.source_draft_id,
                code_task_revision_id=original.code_task_revision_id,
                code_snapshot=dict(original.code_snapshot) if original.code_snapshot else None,
                is_demo=original.is_demo,
            )
        )
    await db.commit()
    await db.refresh(new_session)
    return await _public_with_state(db, quiz=new_session)


@router.put(
    "/quiz-sessions/{session_id}/favorite",
    dependencies=[Depends(csrf_dependency)],
)
async def favorite_quiz_session(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    if not quiz.is_favorite:
        quiz.is_favorite = True
        await db.commit()
    return {"is_favorite": True}


@router.delete(
    "/quiz-sessions/{session_id}/favorite",
    dependencies=[Depends(csrf_dependency)],
)
async def unfavorite_quiz_session(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    if quiz.is_favorite:
        quiz.is_favorite = False
        await db.commit()
    return {"is_favorite": False}


@router.put(
    "/quiz-sessions/{session_id}/questions/{question_id}/draft",
    dependencies=[Depends(csrf_dependency)],
)
async def save_quiz_answer_draft(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    body: QuizDraftRequest,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    if quiz.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="测验已完成，不能再保存草稿")
    question = await _owned_question(db, session_id=session_id, question_id=question_id)
    _validate_draft_shape(question, body.answer)
    draft = await db.scalar(
        select(QuizAnswerDraft)
        .where(
            QuizAnswerDraft.owner_user_id == context.user.id,
            QuizAnswerDraft.session_id == session_id,
            QuizAnswerDraft.question_id == question_id,
        )
        .with_for_update()
    )
    if draft is None:
        if body.base_revision != 0:
            raise HTTPException(status_code=409, detail="答案草稿版本已变化，请重新读取")
        draft = QuizAnswerDraft(
            owner_user_id=context.user.id,
            session_id=session_id,
            question_id=question_id,
            answer=body.answer,
            revision=1,
        )
        db.add(draft)
    else:
        if body.base_revision != draft.revision:
            raise HTTPException(status_code=409, detail="答案草稿已在其他窗口更新，请重新读取")
        if body.answer == draft.answer:
            latest_attempt = await db.scalar(
                select(QuizAttempt)
                .where(
                    QuizAttempt.owner_user_id == context.user.id,
                    QuizAttempt.session_id == session_id,
                    QuizAttempt.question_id == question_id,
                    QuizAttempt.attempt_no.is_not(None),
                )
                .order_by(QuizAttempt.created_at.desc())
            )
            await db.commit()
            return {
                "draft": {
                    "question_id": str(question_id),
                    "answer": draft.answer,
                    "revision": draft.revision,
                    "updated_at": draft.updated_at,
                },
                "last_submitted_answer": latest_attempt.answer if latest_attempt else None,
            }
        draft.answer = body.answer
        draft.revision += 1
    await db.commit()
    await db.refresh(draft)
    latest_attempt = await db.scalar(
        select(QuizAttempt)
        .where(
            QuizAttempt.owner_user_id == context.user.id,
            QuizAttempt.session_id == session_id,
            QuizAttempt.question_id == question_id,
            QuizAttempt.attempt_no.is_not(None),
        )
        .order_by(QuizAttempt.created_at.desc())
    )
    return {
        "draft": {
            "question_id": str(question_id),
            "answer": draft.answer,
            "revision": draft.revision,
            "updated_at": draft.updated_at,
        },
        "last_submitted_answer": latest_attempt.answer if latest_attempt else None,
    }


@router.patch(
    "/quiz-sessions/{session_id}/position",
    dependencies=[Depends(csrf_dependency)],
)
async def save_quiz_position(
    session_id: uuid.UUID,
    body: QuizPositionPatch,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    if body.position >= quiz.question_count:
        raise HTTPException(status_code=422, detail="题号超出本次练习范围")
    quiz.current_position = body.position
    await db.commit()
    return {"position": quiz.current_position}


@router.get("/quiz-sessions/{session_id}/history")
async def read_quiz_history(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    snapshot = await session_snapshot(db, session=quiz)
    attempts = [
        {
            "id": str(attempt.id),
            "question_id": str(attempt.question_id),
            "answer": attempt.answer,
            "outcome": attempt.outcome,
            "is_correct": attempt.is_correct,
            "attempt_no": attempt.attempt_no,
            "created_at": attempt.created_at,
        }
        for rows in snapshot["attempts"].values()
        for attempt in rows
    ]
    runs = list(
        await db.scalars(
            select(CodeRun)
            .where(CodeRun.quiz_session_id == quiz.id, CodeRun.owner_user_id == context.user.id)
            .order_by(CodeRun.created_at)
        )
    )
    return {
        "quiz_session_id": str(quiz.id),
        "attempts": attempts,
        "code_submissions": [
            {
                "id": str(run.id),
                "question_id": str(run.question_id) if run.question_id else None,
                "purpose": run.purpose,
                "status": run.status,
                "correctness_status": run.correctness_status,
                "deterministic_score": run.deterministic_score,
                "code": run.code,
                "created_at": run.created_at,
                "completed_at": run.completed_at,
            }
            for run in runs
        ],
    }


@router.get("/quiz-sessions/{session_id}/result")
async def read_quiz_result(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return a completed practice result calculated from trusted server rows."""
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    if quiz.status != "COMPLETED":
        raise HTTPException(status_code=409, detail="练习尚未完成")
    snapshot = await session_snapshot(db, session=quiz)
    code_runs = list(
        await db.scalars(
            select(CodeRun)
            .where(
                CodeRun.owner_user_id == context.user.id,
                CodeRun.quiz_session_id == quiz.id,
                CodeRun.purpose == "GRADE",
                CodeRun.status.not_in(
                    ("QUEUED", "RUNNING", "CANCELLED", "UNAVAILABLE", "SYSTEM_ERROR")
                ),
                CodeRun.correctness_status.in_(("PASSED", "PARTIAL", "FAILED")),
            )
            .order_by(CodeRun.created_at, CodeRun.id)
        )
    )
    runs_by_question = {run.question_id: run for run in code_runs if run.question_id is not None}
    first_runs_by_question: dict[uuid.UUID, CodeRun] = {}
    for run in code_runs:
        if run.question_id is not None:
            first_runs_by_question.setdefault(run.question_id, run)
    questions: list[dict[str, Any]] = []
    correct_count = 0
    first_correct_count = 0
    for question in snapshot["questions"]:
        attempts = snapshot["attempts"].get(question.id, [])
        run = runs_by_question.get(question.id) if question.type == "CODE" else None
        first_run = first_runs_by_question.get(question.id) if run is not None else None
        final_correct = (
            run.correctness_status == "PASSED"
            if run is not None
            else (attempts[-1].is_correct is True if attempts else False)
        )
        first_correct = (
            first_run.correctness_status == "PASSED"
            if first_run is not None
            else (attempts[0].is_correct is True if attempts else False)
        )
        correct_count += int(final_correct)
        first_correct_count += int(first_correct)
        questions.append(
            {
                "id": str(question.id),
                "position": question.position,
                "type": question.type,
                "stem": question.stem,
                "first_answer": attempts[0].answer if attempts else None,
                "last_answer": attempts[-1].answer if attempts else None,
                "first_correct": first_correct if attempts or first_run is not None else None,
                "is_correct": final_correct,
                "attempts_used": len(attempts),
                "hints_used": snapshot["hints"].get(question.id, 0),
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
                "source_refs": list(question.source_refs or []),
                "code_result": (
                    {
                        "correctness_status": run.correctness_status,
                        "deterministic_score": run.deterministic_score,
                    }
                    if run is not None
                    else None
                ),
            }
        )
    return {
        "session_id": str(quiz.id),
        "source_conversation_id": str(quiz.source_conversation_id)
        if quiz.source_conversation_id
        else None,
        "source_message_id": str(quiz.source_message_id) if quiz.source_message_id else None,
        "status": quiz.status,
        "scoring_version": quiz.scoring_version,
        "correct": correct_count,
        "first_correct": first_correct_count,
        "total": quiz.question_count,
        "score_percent": (100 * correct_count + quiz.question_count // 2) // quiz.question_count,
        "questions": questions,
        "completed_at": quiz.completed_at,
    }


@router.post(
    "/quiz-sessions/{session_id}/questions/{question_id}/answers",
    dependencies=[Depends(csrf_dependency)],
)
async def answer_question(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    body: AnswerCreate,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    question = await _owned_question(db, session_id=session_id, question_id=question_id)
    try:
        outcome = await submit_answer(
            db,
            session=quiz,
            question=question,
            answer=body.answer,
            idempotency_key=body.idempotency_key,
        )
    except QuizRequestRejected as caught:
        _raise(caught)
    snapshot = await session_snapshot(db, session=quiz)
    return {
        "outcome": outcome.outcome,
        "is_correct": outcome.is_correct,
        "attempts_used": outcome.attempts_used,
        "max_attempts": outcome.max_attempts,
        "correct_answer": outcome.correct_answer,
        "explanation": outcome.explanation,
        "idempotent_replay": outcome.idempotent_replay,
        "session_status": outcome.session_status,
        "progress": {
            "answered": sum(1 for rows in snapshot["attempts"].values() if rows),
            "total": quiz.question_count,
        },
    }


@router.post(
    "/quiz-sessions/{session_id}/questions/{question_id}/hints",
    dependencies=[Depends(csrf_dependency)],
)
async def request_question_hint(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    body: HintCreate,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    question = await _owned_question(db, session_id=session_id, question_id=question_id)
    try:
        return await request_hint(
            db,
            session=quiz,
            question=question,
            level=body.level,
            idempotency_key=body.idempotency_key,
        )
    except QuizRequestRejected as caught:
        _raise(caught)


@router.get("/quiz-sessions/{session_id}/review")
async def read_quiz_review(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    return await review_overview(db, session=quiz)
