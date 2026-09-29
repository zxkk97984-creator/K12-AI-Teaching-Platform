"""HTTP/JSON projections. Answers never appear in any projection (T15 G4/G8)."""

from __future__ import annotations

from typing import Any

from app.modules.assessment.models import GenerationJob, QuizDraft


def job_public(job: GenerationJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "operation": job.operation,
        "purpose": job.purpose,
        "status": job.status,
        "error_code": job.error_code,
        "error_detail": job.error_detail,
        "chapter_id": str(job.chapter_id) if job.chapter_id else None,
        "revision_id": str(job.revision_id) if job.revision_id else None,
        "source_conversation_id": str(job.source_conversation_id)
        if job.source_conversation_id
        else None,
        "source_message_id": str(job.source_message_id) if job.source_message_id else None,
        "gateway_mode": job.gateway_mode,
        "fixture": job.fixture,
        "fixture_allowance": job.fixture_allowance,
        "gateway_invocation_id": job.gateway_invocation_id,
        "request_id": job.request_id,
        "request_hash": job.request_hash,
        "request_config": job.request_config,
        "quiz_session_id": str(job.quiz_session_id) if job.quiz_session_id else None,
        "usage": job.usage,
        "request_summary": job.request_summary,
        "created_at": job.created_at.isoformat(),
    }


def draft_public(draft: QuizDraft) -> dict[str, Any]:
    return {
        "id": str(draft.id),
        "job_id": str(draft.job_id),
        "chapter_id": str(draft.chapter_id) if draft.chapter_id else None,
        "revision_id": str(draft.revision_id) if draft.revision_id else None,
        "source_conversation_id": str(draft.source_conversation_id)
        if draft.source_conversation_id
        else None,
        "curriculum_revision": draft.curriculum_revision,
        "stage": draft.stage,
        "request_id": draft.request_id,
        "status": draft.status,
        "origin": draft.origin,
        "difficulty": draft.difficulty,
        "question_count": draft.question_count,
        "question_types": list(draft.question_types or []),
        "validation_passed": draft.validation_passed,
        "validation": draft.validation,
        "reviewed": {
            "reviewer_subject_id": str(draft.review_subject_id)
            if draft.review_subject_id
            else None,
            "reviewed_at": draft.reviewed_at.isoformat() if draft.reviewed_at else None,
            "note": draft.review_note,
        },
        # Student-safe projection (stems/options/items only). ``draft`` - the
        # server-side object that carries answers - is never projected here.
        "student_projection": draft.student_projection,
        "created_at": draft.created_at.isoformat(),
    }
