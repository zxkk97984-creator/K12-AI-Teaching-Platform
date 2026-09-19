"""Student quiz API (T16). The practice UI itself ships with T17."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.assessment.errors import AssessmentError
from app.modules.assessment.models import QuizQuestion, QuizSession
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
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.identity.models import LearnerProfile

router = APIRouter(tags=["assessment"])

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
    snapshot = await session_snapshot(db, session=quiz)
    return session_public(
        quiz,
        questions=snapshot["questions"],
        attempts=snapshot["attempts"],
        hints=snapshot["hints"],
    )


@router.get("/quiz-sessions/{session_id}")
async def read_quiz_session(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    quiz = await _owned_session(db, owner_id=context.user.id, session_id=session_id)
    snapshot = await session_snapshot(db, session=quiz)
    return session_public(
        quiz,
        questions=snapshot["questions"],
        attempts=snapshot["attempts"],
        hints=snapshot["hints"],
    )


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
