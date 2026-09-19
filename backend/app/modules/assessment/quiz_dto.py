"""Student-facing quiz projections (T16 H3/H9).

``question_public`` never emits ``correct_answer`` or ``explanation`` before the
student has a scored attempt for that question; after the attempt the released
feedback carries the answer and the explanation for *that* question only.
"""

from __future__ import annotations

from typing import Any

from app.modules.assessment.models import QuizAttempt, QuizQuestion, QuizSession

TRUE_FALSE_OPTIONS = [
    {"key": "TRUE", "text": "对"},
    {"key": "FALSE", "text": "错"},
]


def _hint_limit(question: QuizQuestion, session: QuizSession) -> int:
    return min(session.max_hints, len(question.hints or []))


def question_public(
    question: QuizQuestion,
    *,
    session: QuizSession,
    attempts: list[QuizAttempt],
    hints_used: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        # Client-visible identifier: the answer/hint routes take this UUID.
        "id": str(question.id),
        "question_key": question.question_key,
        "position": question.position,
        "type": question.type,
        "stem": question.stem,
        "source_refs": list(question.source_refs or []),
        "hint_limit": _hint_limit(question, session),
        "hints_used": hints_used,
        "hints": list(question.hints or [])[:hints_used],  # only released levels
        "attempts_used": len(attempts),
        "max_attempts": session.max_attempts,
    }
    if question.type == "SINGLE_CHOICE":
        payload["options"] = list(question.options or [])
    elif question.type == "TRUE_FALSE":
        payload["options"] = list(TRUE_FALSE_OPTIONS)
    else:
        payload["items"] = list(question.items or [])

    if attempts:
        last = attempts[-1]
        payload["feedback"] = {
            "outcome": last.outcome,
            "is_correct": last.is_correct,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
            "attempts_used": len(attempts),
            "max_attempts": session.max_attempts,
        }
    return payload


def session_public(
    session: QuizSession,
    *,
    questions: list[QuizQuestion],
    attempts: dict[Any, list[QuizAttempt]],
    hints: dict[Any, int],
) -> dict[str, Any]:
    projected = [
        question_public(
            question,
            session=session,
            attempts=attempts.get(question.id, []),
            hints_used=hints.get(question.id, 0),
        )
        for question in questions
    ]
    answered = sum(1 for question in questions if attempts.get(question.id))
    correct = sum(
        1
        for question in questions
        if attempts.get(question.id) and attempts[question.id][-1].is_correct is True
    )
    return {
        "id": str(session.id),
        "chapter_id": str(session.chapter_id),
        "revision_id": str(session.revision_id),
        "curriculum_revision": session.curriculum_revision,
        "stage": session.stage,
        "status": session.status,
        "source_kind": session.source_kind,
        "source_label": session.source_label,
        "difficulty": session.difficulty,
        "question_count": session.question_count,
        "max_attempts": session.max_attempts,
        "max_hints": session.max_hints,
        "scoring_version": session.scoring_version,
        "thresholds_version": session.thresholds_version,
        "base_revision": session.base_revision,
        "created_at": session.created_at.isoformat(),
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "progress": {
            "answered": answered,
            "correct": correct,
            "total": session.question_count,
        },
        "questions": projected,
        "notices": (
            ["题目来自 AI 生成草稿（未人工审校），仅用于私人随堂练习。"]
            if session.source_kind == "AI_DRAFT"
            else ["题目来自人工审校题源。"]
        ),
    }
