"""Resolve bounded, owned answer evidence to actionable immutable quiz targets."""

import uuid

from sqlalchemy import select

from app.modules.assessment.models import QuizQuestion, QuizSession
from app.modules.learning.models import CORRECT_OUTCOMES
from app.modules.recommendation.decision import ObjectiveState


async def objective_states(db, *, owner_user_id, stage, answers):
    ids = {
        uuid.UUID(item.source_ref["question_id"])
        for item in answers
        if item.source_ref.get("question_id")
    }
    if not ids:
        return ()
    rows = (
        await db.execute(
            select(QuizQuestion, QuizSession)
            .join(QuizSession, QuizQuestion.session_id == QuizSession.id)
            .where(
                QuizQuestion.id.in_(ids),
                QuizSession.owner_user_id == owner_user_id,
                QuizSession.stage == stage,
            )
        )
    ).all()
    targets = {str(question.id): (question, quiz) for question, quiz in rows}
    grouped = {}
    for item in sorted(answers, key=lambda row: (row.observed_at, str(row.id)), reverse=True):
        target = targets.get(item.source_ref.get("question_id"))
        if target is None or target[0].objective_id != item.objective_id:
            continue
        grouped.setdefault(item.objective_id, []).append((item, *target))
    answered_by_quiz = {}
    for records in grouped.values():
        for _item, question, quiz in records:
            answered_by_quiz.setdefault(quiz.id, set()).add(question.id)
    result = []
    for objective, records in sorted(grouped.items()):
        latest = {}
        for item, question, quiz in records:
            # Repeating a snapshot changes IDs, but retains its source and question key.
            source = quiz.draft_id or quiz.source_message_id or quiz.revision_id or quiz.id
            latest.setdefault((str(source), question.question_key), (item, question, quiz))
        wrong = [entry for entry in latest.values() if entry[0].outcome not in CORRECT_OUTCOMES]
        item, question, quiz = wrong[0] if wrong else records[0]
        correct = sum(entry[0].outcome in CORRECT_OUTCOMES for entry in records)
        result.append(
            ObjectiveState(
                objective_id=objective,
                answered=len(records),
                incorrect=len(wrong),
                level="CONSISTENT" if correct >= 2 and not wrong else "EMERGING",
                last_incorrect_evidence_id=str(item.id) if wrong else None,
                evidence_ids=tuple(str(entry[0].id) for entry in records),
                quiz_session_id=str(quiz.id),
                question_id=str(question.id),
                question_position=question.position,
                quiz_status=quiz.status,
                quiz_answered=len(answered_by_quiz.get(quiz.id, ())),
                quiz_title=quiz.source_title or question.stem,
            )
        )
    return tuple(result)
