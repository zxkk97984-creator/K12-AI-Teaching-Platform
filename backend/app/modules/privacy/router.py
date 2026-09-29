from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.assessment.models import QuizAnswerDraft
from app.modules.codelab.models import CodeDraft, CodeRun, CodeTaskFavorite
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.identity.models import LearnerProfile
from app.modules.learning.models import LearningBookmark, LearningOpenEvent
from app.modules.memory.models import MemoryContextState, MemoryDocument
from app.modules.privacy.models import PrivacyDeletionRequest
from app.modules.teaching.models import LessonSession

router = APIRouter(tags=["privacy"])


class DeletionRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=160)


def _redact_untrusted_result(value: Any) -> Any:
    if isinstance(value, dict):
        blocked = {"expected", "hidden_tests", "reference_solution", "test_manifest", "rubric"}
        return {
            key: _redact_untrusted_result(item) for key, item in value.items() if key not in blocked
        }
    if isinstance(value, list):
        return [_redact_untrusted_result(item) for item in value]
    return copy.deepcopy(value)


def _deletion_view(row: PrivacyDeletionRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "idempotency_key": row.idempotency_key,
        "status": row.status,
        "platform_status": row.platform_status,
        "scope": row.scope,
        "requested_at": row.requested_at,
        "completed_at": row.completed_at,
    }


@router.get("/me/data-export")
async def export_my_data(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    drafts = (
        await db.scalars(
            select(CodeDraft)
            .where(CodeDraft.owner_user_id == context.user.id)
            .order_by(CodeDraft.updated_at, CodeDraft.id)
        )
    ).all()
    runs = (
        await db.scalars(
            select(CodeRun)
            .where(CodeRun.owner_user_id == context.user.id)
            .order_by(CodeRun.created_at, CodeRun.id)
        )
    ).all()
    code_favorites = (
        await db.scalars(
            select(CodeTaskFavorite)
            .where(CodeTaskFavorite.owner_user_id == context.user.id)
            .order_by(CodeTaskFavorite.created_at, CodeTaskFavorite.task_id)
        )
    ).all()
    conversations = (
        await db.scalars(
            select(LessonSession)
            .where(LessonSession.owner_user_id == context.user.id)
            .order_by(LessonSession.created_at, LessonSession.id)
        )
    ).all()
    documents = (
        await db.scalars(
            select(MemoryDocument)
            .where(MemoryDocument.owner_user_id == context.user.id)
            .order_by(MemoryDocument.created_at, MemoryDocument.id)
        )
    ).all()
    bookmarks = (
        await db.scalars(
            select(LearningBookmark)
            .where(LearningBookmark.owner_user_id == context.user.id)
            .order_by(LearningBookmark.created_at, LearningBookmark.id)
        )
    ).all()
    open_events = (
        await db.scalars(
            select(LearningOpenEvent)
            .where(LearningOpenEvent.owner_user_id == context.user.id)
            .order_by(LearningOpenEvent.created_at, LearningOpenEvent.id)
        )
    ).all()
    quiz_drafts = (
        await db.scalars(
            select(QuizAnswerDraft)
            .where(QuizAnswerDraft.owner_user_id == context.user.id)
            .order_by(QuizAnswerDraft.updated_at, QuizAnswerDraft.id)
        )
    ).all()
    return {
        "schema_version": "k12.local-data-export.v1",
        "exported_at": datetime.now(UTC),
        "identity": {
            "id": context.user.id,
            "username": context.user.username,
            "role": context.user.role,
        },
        "profile": {
            "stage": profile.stage,
            "grade": profile.grade,
            "preferred_style": profile.preferred_style,
            "interests": profile.interests,
            "proactive_guidance_enabled": profile.proactive_guidance_enabled,
            "voice_preference": profile.voice_preference,
            "revision": profile.revision,
        }
        if profile
        else None,
        "codelab": {
            "drafts": [
                {
                    "task_id": row.task_id,
                    "task_revision": row.task_revision,
                    "code": row.code,
                    "code_hash": row.code_sha256,
                    "lesson_session_id": row.lesson_session_id,
                    "updated_at": row.updated_at,
                }
                for row in drafts
            ],
            "runs": [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "task_revision": row.task_revision,
                    "code": row.code,
                    "code_hash": row.code_sha256,
                    "status": row.status,
                    "execution_status": row.execution_status,
                    "correctness_status": row.correctness_status,
                    "deterministic_score": row.deterministic_score,
                    "result": _redact_untrusted_result(row.result),
                    "feedback_status": row.feedback_status,
                    "feedback": _redact_untrusted_result(row.feedback),
                    "created_at": row.created_at,
                    "completed_at": row.completed_at,
                }
                for row in runs
            ],
            "favorites": [
                {"task_id": row.task_id, "created_at": row.created_at} for row in code_favorites
            ],
        },
        "conversations": [
            {
                "id": row.id,
                "conversation_type": row.conversation_type,
                "title": row.title,
                "chapter_id": row.chapter_id,
                "stage": row.stage,
                "created_at": row.created_at,
                "context": row.context,
            }
            for row in conversations
        ],
        "learning": {
            "bookmarks": [
                {
                    "target_kind": row.target_kind,
                    "target_id": row.target_id,
                    "target_title": row.target_title,
                    "created_at": row.created_at,
                }
                for row in bookmarks
            ],
            "open_events": [
                {
                    "target_kind": row.target_kind,
                    "target_id": row.target_id,
                    "target_title": row.target_title,
                    "target_version": row.target_version,
                    "created_at": row.created_at,
                }
                for row in open_events
            ],
        },
        "memory_documents": [
            {
                "id": row.id,
                "title": row.title,
                "category": row.category,
                "content_markdown": row.content_markdown,
                "revision": row.revision,
                "ai_enabled": row.ai_enabled,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in documents
        ],
        "assessment": {
            "answer_drafts": [
                {
                    "session_id": row.session_id,
                    "question_id": row.question_id,
                    "answer": row.answer,
                    "revision": row.revision,
                    "updated_at": row.updated_at,
                }
                for row in quiz_drafts
            ]
        },
        "scope": {
            "included": [
                "identity.profile",
                "codelab.drafts",
                "codelab.runs",
                "teaching.conversations",
                "learning.bookmarks",
                "learning.open_events",
                "memory.documents",
                "assessment.answer_drafts",
            ],
            "excluded": [
                "password_hashes",
                "session_tokens",
                "trusted_hidden_tests",
                "reference_solutions",
                "Knodo files and remote tool history",
            ],
            "platform_status": "NOT_CONNECTED",
            "note": "这是本地数据导出；平台侧文件和远端会话未接入，不能由本地接口声称已导出。",
        },
    }


@router.get("/me/deletion-requests")
async def list_my_deletion_requests(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = (
        await db.scalars(
            select(PrivacyDeletionRequest)
            .where(PrivacyDeletionRequest.owner_user_id == context.user.id)
            .order_by(PrivacyDeletionRequest.requested_at.desc())
        )
    ).all()
    return {"items": [_deletion_view(row) for row in rows]}


@router.post("/me/deletion-requests", dependencies=[Depends(csrf_dependency)])
async def request_local_deletion(
    payload: DeletionRequestCreate,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    existing = await db.scalar(
        select(PrivacyDeletionRequest).where(
            PrivacyDeletionRequest.owner_user_id == context.user.id,
            PrivacyDeletionRequest.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return {"request": _deletion_view(existing), "idempotent_replay": True}

    deleted_drafts = await db.execute(
        delete(CodeDraft).where(CodeDraft.owner_user_id == context.user.id)
    )
    deleted_runs = await db.execute(delete(CodeRun).where(CodeRun.owner_user_id == context.user.id))
    deleted_code_favorites = await db.execute(
        delete(CodeTaskFavorite).where(CodeTaskFavorite.owner_user_id == context.user.id)
    )
    deleted_conversations = await db.execute(
        delete(LessonSession).where(LessonSession.owner_user_id == context.user.id)
    )
    deleted_open_events = await db.execute(
        delete(LearningOpenEvent).where(LearningOpenEvent.owner_user_id == context.user.id)
    )
    deleted_bookmarks = await db.execute(
        delete(LearningBookmark).where(LearningBookmark.owner_user_id == context.user.id)
    )
    deleted_documents = await db.execute(
        delete(MemoryDocument).where(MemoryDocument.owner_user_id == context.user.id)
    )
    deleted_context = await db.execute(
        delete(MemoryContextState).where(MemoryContextState.owner_user_id == context.user.id)
    )
    deleted_quiz_drafts = await db.execute(
        delete(QuizAnswerDraft).where(QuizAnswerDraft.owner_user_id == context.user.id)
    )
    now = datetime.now(UTC)
    row = PrivacyDeletionRequest(
        owner_user_id=context.user.id,
        idempotency_key=payload.idempotency_key,
        status="LOCAL_COMPLETED",
        platform_status="NOT_REQUESTED",
        scope={
            "requested_scope": "LOCAL_STUDENT_DATA",
            "local": {
                "codelab_code_drafts": deleted_drafts.rowcount or 0,
                "codelab_code_runs": deleted_runs.rowcount or 0,
                "codelab_task_favorites": deleted_code_favorites.rowcount or 0,
                "teaching_conversations": deleted_conversations.rowcount or 0,
                "learning_open_events": deleted_open_events.rowcount or 0,
                "learning_bookmarks": deleted_bookmarks.rowcount or 0,
                "memory_documents": deleted_documents.rowcount or 0,
                "memory_context_states": deleted_context.rowcount or 0,
                "assessment_answer_drafts": deleted_quiz_drafts.rowcount or 0,
            },
            "platform": {
                "status": "NOT_REQUESTED",
                "reason": "Knodo is not connected in this local profile",
            },
        },
        requested_at=now,
        completed_at=now,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"request": _deletion_view(row), "idempotent_replay": False}
