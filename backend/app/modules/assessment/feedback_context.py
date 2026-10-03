"""Only scored feedback for the referenced question may reach its Tutor."""

import uuid

from sqlalchemy import select

from app.modules.assessment.models import QuizAttempt, QuizQuestion


async def released_question_feedback(db, *, session_id, owner_id, question_id):
    try:
        question_id = uuid.UUID(str(question_id))
    except (ValueError, TypeError):
        return None
    question = await db.scalar(
        select(QuizQuestion)
        .join(QuizAttempt, QuizAttempt.question_id == QuizQuestion.id)
        .where(
            QuizQuestion.id == question_id,
            QuizQuestion.session_id == session_id,
            QuizAttempt.session_id == session_id,
            QuizAttempt.owner_user_id == owner_id,
            QuizAttempt.attempt_no.is_not(None),
        )
        .limit(1)
    )
    if question is None:
        return None
    return (
        f"该题已由服务器批改，以下解析已向该学生公开："
        f"第 {question.position + 1} 题：{question.stem[:300]}；"
        f"解析：{(question.explanation or '')[:1800]}"
    )
