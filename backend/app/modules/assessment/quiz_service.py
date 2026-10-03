"""Quiz sessions, deterministic scoring, hints and review links (T16).

Transaction discipline (H7): the attempt/hint row, its trusted learning event,
the review link and the session terminal transition are written in one short
transaction. Idempotency uses a DB unique constraint, never a process lock, so
a replay returns the stored verdict without adding a second attempt or event.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.assessment.errors import AssessmentError
from app.modules.assessment.models import (
    QuizAttempt,
    QuizDraft,
    QuizHintEvent,
    QuizQuestion,
    QuizReviewLink,
    QuizSession,
)
from app.modules.assessment.scoring import (
    REVIEW_THRESHOLDS_VERSION,
    SCORING_VERSION,
    AnswerRejected,
    ScoringUnavailable,
    score_answer,
)
from app.modules.codelab.models import CodeRun, CodeTaskRevision
from app.modules.content.models import (
    Chapter,
    ChapterReviewState,
    ChapterRevision,
    KnowledgePoint,
    Release,
    RevisionKnowledgePoint,
)
from app.modules.content.service import viewer_scope_from_profile, visible_chapter_detail
from app.modules.identity.models import LearnerProfile, User, UserRole
from app.modules.learning.models import QuizEvidence
from app.modules.learning.policy import build_policy, evidence_level_from

SOURCE_LABELS = {
    "HUMAN_REVIEWED": "人工审校题目",
    "AI_DRAFT": "AI 生成草稿（未人工审校），仅用于私人随堂练习",
}
AI_ORIGINS = ("FIXTURE", "MODEL_DRAFT")


class QuizSourceUnavailable(AssessmentError):
    """No approved/validated draft fits this chapter and policy (QA17)."""

    code = "NO_QUESTIONS_AVAILABLE"


class QuizRequestRejected(AssessmentError):
    """The client request cannot be served (limits, terminal state, conflict)."""

    code = "QUIZ_REQUEST_REJECTED"


@dataclass(frozen=True)
class AttemptOutcome:
    attempt_id: uuid.UUID
    outcome: str
    is_correct: bool | None
    attempt_no: int | None
    attempts_used: int
    max_attempts: int
    explanation: str
    correct_answer: object
    idempotent_replay: bool
    session_status: str


def _hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _presentation_items(
    question_key: str, items: list[dict], correct_order: list[str]
) -> list[dict]:
    """Deterministic presentation order that never equals the stored answer."""

    by_key = {item["key"]: item for item in items}
    ranked = sorted(
        by_key,
        key=lambda key: hashlib.sha256(f"{question_key}|{key}".encode()).hexdigest(),
    )
    if ranked == list(correct_order) and len(ranked) > 1:
        ranked = ranked[1:] + ranked[:1]
    return [by_key[key] for key in ranked]


async def quiz_evidence_level(db: AsyncSession, *, owner_user_id: uuid.UUID) -> str:
    """Evidence level from real quiz answers only (never from hints/skips)."""

    rows = (
        await db.execute(
            select(QuizEvidence.outcome).where(
                QuizEvidence.owner_user_id == owner_user_id,
                QuizEvidence.kind == "QUIZ_ANSWERED",
            )
        )
    ).all()
    real = len(rows)
    correct = len([row for row in rows if row[0] == "CORRECT"])
    return evidence_level_from(real_activities=real, correct_activities=correct)


async def _chapter_material(
    db: AsyncSession, *, chapter_id: uuid.UUID, revision_id: uuid.UUID | None = None
):
    row = (
        await db.execute(
            select(ChapterRevision, Chapter, Release, ChapterReviewState)
            .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
            .join(Release, Release.id == ChapterRevision.release_id)
            .join(ChapterReviewState, ChapterReviewState.revision_id == ChapterRevision.id)
            .where(
                ChapterRevision.chapter_id == chapter_id,
                *([ChapterRevision.id == revision_id] if revision_id is not None else []),
            )
            .order_by(ChapterRevision.revision.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise QuizSourceUnavailable("章节没有可用版本")
    revision, chapter, release, review_state = row
    if review_state.publication_status == "WITHDRAWN":
        raise QuizSourceUnavailable("章节版本已撤回")
    knowledge_points = (
        (
            await db.execute(
                select(KnowledgePoint.stable_slug)
                .join(
                    RevisionKnowledgePoint,
                    RevisionKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
                )
                .where(RevisionKnowledgePoint.revision_id == revision.id)
                .order_by(KnowledgePoint.stable_slug)
            )
        )
        .scalars()
        .all()
    )
    return revision, chapter, release, list(knowledge_points)


async def _candidate_drafts(
    db: AsyncSession, *, chapter_id: uuid.UUID, revision_id: uuid.UUID, owner_id: uuid.UUID
) -> list[QuizDraft]:
    rows = await db.scalars(
        select(QuizDraft)
        .join(User, User.id == QuizDraft.owner_user_id)
        .where(
            QuizDraft.chapter_id == chapter_id,
            QuizDraft.revision_id == revision_id,
            QuizDraft.validation_passed.is_(True),
            QuizDraft.status.in_(("HUMAN_APPROVED", "AUTO_VALIDATED")),
            or_(QuizDraft.owner_user_id == owner_id, User.role == UserRole.ADMIN.value),
        )
        .order_by(
            # human-reviewed sources first, then newest validated drafts
            (QuizDraft.status != "HUMAN_APPROVED"),
            QuizDraft.created_at.desc(),
        )
    )
    return list(rows)


def _draft_fits_policy(draft: QuizDraft, payload: dict, policy) -> str | None:
    """Return a rejection code, or None when the draft may be used."""

    questions = payload.get("questions") or []
    if not questions:
        return "EMPTY_DRAFT"
    if draft.stage != policy.stage:
        return "STAGE_MISMATCH"
    if payload.get("difficulty") not in policy.allowed_difficulties:
        return "DIFFICULTY_NOT_ALLOWED"
    if len(questions) > policy.max_quiz_questions:
        return "COUNT_NOT_ALLOWED"
    for question in questions:
        if question.get("type") not in policy.allowed_question_types:
            return "TYPE_NOT_ALLOWED"
    return None


async def create_quiz_session(
    db: AsyncSession,
    *,
    settings: Settings,
    requester: User,
    profile: LearnerProfile | None,
    chapter_id: uuid.UUID | None,
    draft_id: uuid.UUID | None = None,
    revision_id: uuid.UUID | None = None,
    source_conversation_id: uuid.UUID | None = None,
    source_message_id: uuid.UUID | None = None,
    source_title: str = "",
    code_task_ref: dict | None = None,
    commit: bool = True,
) -> QuizSession:
    if profile is None or not profile.stage:
        raise QuizRequestRejected("请先完成学段设置再开始练习", code="STAGE_REQUIRED")
    if chapter_id is None and source_conversation_id is not None:
        if revision_id is not None or draft_id is None:
            raise QuizRequestRejected("会话练习来源无效")
        revision = SimpleNamespace(id=None, stage=profile.stage)
        knowledge_points: list[str] = []
    else:
        if chapter_id is None:
            raise QuizRequestRejected("练习来源不能为空")
        viewer = viewer_scope_from_profile(profile, settings)
        detail = await visible_chapter_detail(db, chapter_id=chapter_id, viewer=viewer)
        if detail is None:
            raise QuizSourceUnavailable("章节对当前学段不可用", code="CHAPTER_NOT_VISIBLE")
        revision, _chapter, _release, knowledge_points = await _chapter_material(
            db, chapter_id=chapter_id, revision_id=revision_id
        )
        if revision.stage != profile.stage:
            raise QuizSourceUnavailable("章节学段与学生档案不一致", code="STAGE_MISMATCH")

    level = await quiz_evidence_level(db, owner_user_id=requester.id)
    policy = build_policy(
        stage=profile.stage,
        grade=profile.grade,
        preferred_style=profile.preferred_style,
        evidence_level=level,
        proactive_guidance_enabled=profile.proactive_guidance_enabled,
    )

    chosen: tuple[QuizDraft, dict] | None = None
    rejections: list[str] = []
    if draft_id is not None:
        selected = await db.scalar(
            select(QuizDraft).where(
                QuizDraft.id == draft_id,
                QuizDraft.owner_user_id == requester.id,
                QuizDraft.chapter_id == chapter_id,
                QuizDraft.revision_id == revision.id,
                QuizDraft.source_conversation_id == source_conversation_id,
            )
        )
        candidates = [selected] if selected is not None else []
    else:
        candidates = await _candidate_drafts(
            db, chapter_id=chapter_id, revision_id=revision.id, owner_id=requester.id
        )
    for draft in candidates:
        payload = draft.draft
        if not isinstance(payload, dict):
            rejections.append("DRAFT_PAYLOAD_MISSING")
            continue
        rejection = _draft_fits_policy(draft, payload, policy)
        if rejection is not None:
            rejections.append(rejection)
            continue
        chosen = (draft, payload)
        break
    if chosen is None:
        # QA17: never silently swap in unrelated generic questions.
        detail_text = "当前章节没有符合本学段策略的已校验/已审题稿"
        if rejections:
            detail_text += f"（拒绝原因：{sorted(set(rejections))}）"
        raise QuizSourceUnavailable(detail_text)

    draft, payload = chosen
    questions = list(payload["questions"])
    code_task = None
    if code_task_ref is not None:
        task_id = str(code_task_ref.get("task_id") or "")
        task_revision = int(code_task_ref.get("revision") or 0)
        code_task = await db.scalar(
            select(CodeTaskRevision).where(
                CodeTaskRevision.task_id == task_id,
                CodeTaskRevision.revision == task_revision,
                CodeTaskRevision.status.in_(("DRAFT", "PUBLISHED")),
            )
        )
        binding = dict(code_task.chapter_binding or {}) if code_task else {}
        if code_task is None or binding.get("stage") != revision.stage:
            raise QuizSourceUnavailable("所选编程题当前学段不可用")
        if len(questions) >= policy.max_quiz_questions:
            questions = questions[: max(policy.max_quiz_questions - 1, 0)]
        questions.append({"type": "CODE", "task": code_task})
    source_kind = "HUMAN_REVIEWED" if draft.status == "HUMAN_APPROVED" else "AI_DRAFT"
    session = QuizSession(
        owner_user_id=requester.id,
        chapter_id=chapter_id,
        revision_id=revision.id,
        source_conversation_id=source_conversation_id,
        source_message_id=source_message_id,
        source_title=source_title[:200],
        draft_id=draft.id,
        curriculum_revision=draft.curriculum_revision,
        stage=revision.stage,
        grade=profile.grade,
        source_kind=source_kind,
        source_label=SOURCE_LABELS[source_kind],
        difficulty=payload["difficulty"],
        question_count=len(questions),
        max_attempts=settings.quiz_max_attempts_per_question,
        max_hints=settings.quiz_max_hints_per_question,
        knowledge_point_slugs=knowledge_points,
        scoring_version=SCORING_VERSION,
        thresholds_version=REVIEW_THRESHOLDS_VERSION,
        status="ACTIVE",
    )
    db.add(session)
    await db.flush()

    for position, question in enumerate(questions):
        qtype = question["type"]
        if qtype == "CODE":
            task = question["task"]
            db.add(
                QuizQuestion(
                    session_id=session.id,
                    position=position,
                    question_key=f"code:{task.task_id}:r{task.revision}",
                    objective_id=f"codelab:{task.task_id}",
                    type="CODE",
                    stem=task.description,
                    options=None,
                    items=None,
                    correct_answer=None,
                    explanation=None,
                    hints=["先运行公开样例，再提交正式判题。"],
                    source_refs=[],
                    origin=draft.origin,
                    source_draft_id=draft.id,
                    code_task_revision_id=task.id,
                    code_snapshot={
                        "task_id": task.task_id,
                        "task_revision": task.revision,
                        "title": task.title,
                        "description": task.description,
                        "starter_code": task.starter_code,
                        "entrypoint": task.entrypoint,
                        "examples": task.examples,
                    },
                    is_demo=bool(task.is_test_fixture or task.status == "DRAFT"),
                )
            )
            continue
        correct_answer = (
            question["correct_order"] if qtype == "ORDERING" else question["correct_answer"]
        )
        items = None
        if qtype == "ORDERING":
            items = _presentation_items(
                question["question_key"], question["items"], question["correct_order"]
            )
        db.add(
            QuizQuestion(
                session_id=session.id,
                position=position,
                question_key=question["question_key"],
                objective_id=question["objective_id"],
                type=qtype,
                stem=question["stem"],
                options=question["options"] if qtype == "SINGLE_CHOICE" else None,
                items=items,
                correct_answer=correct_answer,
                explanation=question["explanation"],
                hints=list(question["hints"])[: session.max_hints],
                source_refs=list(question["source_refs"]),
                origin=draft.origin,
                source_draft_id=draft.id,
            )
        )
    if commit:
        await db.commit()
        await db.refresh(session)
    return session


async def get_session(db: AsyncSession, *, session_id: uuid.UUID, owner_id: uuid.UUID):
    return await db.scalar(
        select(QuizSession).where(
            QuizSession.id == session_id, QuizSession.owner_user_id == owner_id
        )
    )


async def get_question(
    db: AsyncSession, *, session_id: uuid.UUID, question_id: uuid.UUID
) -> QuizQuestion | None:
    return await db.scalar(
        select(QuizQuestion).where(
            QuizQuestion.id == question_id, QuizQuestion.session_id == session_id
        )
    )


async def session_questions(db: AsyncSession, *, session_id: uuid.UUID) -> list[QuizQuestion]:
    rows = await db.scalars(
        select(QuizQuestion)
        .where(QuizQuestion.session_id == session_id)
        .order_by(QuizQuestion.position)
    )
    return list(rows)


async def _attempts_by_question(
    db: AsyncSession, *, session_id: uuid.UUID, owner_user_id: uuid.UUID
) -> dict[uuid.UUID, list[QuizAttempt]]:
    rows = await db.scalars(
        select(QuizAttempt)
        .where(
            QuizAttempt.session_id == session_id,
            QuizAttempt.owner_user_id == owner_user_id,
            QuizAttempt.attempt_no.is_not(None),
        )
        .order_by(QuizAttempt.question_id, QuizAttempt.attempt_no)
    )
    grouped: dict[uuid.UUID, list[QuizAttempt]] = {}
    for row in rows:
        grouped.setdefault(row.question_id, []).append(row)
    return grouped


async def _hint_levels(
    db: AsyncSession, *, session_id: uuid.UUID, owner_user_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(QuizHintEvent.question_id, func.count())
        .where(
            QuizHintEvent.session_id == session_id,
            QuizHintEvent.owner_user_id == owner_user_id,
        )
        .group_by(QuizHintEvent.question_id)
    )
    return {question_id: int(count) for question_id, count in rows.all()}


async def session_snapshot(db: AsyncSession, *, session: QuizSession) -> dict:
    questions = await session_questions(db, session_id=session.id)
    attempts = await _attempts_by_question(
        db, session_id=session.id, owner_user_id=session.owner_user_id
    )
    hints = await _hint_levels(db, session_id=session.id, owner_user_id=session.owner_user_id)
    return {"questions": questions, "attempts": attempts, "hints": hints}


def _record_evidence(
    db: AsyncSession,
    *,
    session: QuizSession,
    kind: str,
    outcome: str,
    source_event_id: uuid.UUID,
    question: QuizQuestion | None = None,
) -> None:
    db.add(
        QuizEvidence(
            owner_user_id=session.owner_user_id,
            quiz_session_id=session.id,
            question_id=question.id if question is not None else None,
            source_event_id=source_event_id,
            kind=kind,
            outcome=outcome,
            objective_id=question.objective_id if question is not None else None,
            knowledge_point_slugs=list(session.knowledge_point_slugs or []),
            thresholds_version=session.thresholds_version,
        )
    )


async def _completed(db: AsyncSession, *, session: QuizSession) -> bool:
    answered = int(
        await db.scalar(
            select(func.count(func.distinct(QuizAttempt.question_id))).where(
                QuizAttempt.session_id == session.id, QuizAttempt.attempt_no.is_not(None)
            )
        )
        or 0
    )
    code_answered = int(
        await db.scalar(
            select(func.count(func.distinct(CodeRun.question_id))).where(
                CodeRun.quiz_session_id == session.id,
                CodeRun.purpose == "GRADE",
                CodeRun.status.not_in(
                    ("QUEUED", "RUNNING", "CANCELLED", "UNAVAILABLE", "SYSTEM_ERROR")
                ),
                CodeRun.correctness_status.in_(("PASSED", "PARTIAL", "FAILED")),
            )
        )
        or 0
    )
    return answered + code_answered >= session.question_count


async def submit_answer(
    db: AsyncSession,
    *,
    session: QuizSession,
    question: QuizQuestion,
    answer: object,
    idempotency_key: str,
) -> AttemptOutcome:
    if question.type == "CODE":
        raise QuizRequestRejected("编程题必须通过代码运行提交", code="INVALID_ANSWER")
    await db.refresh(session, with_for_update=True)
    # Scalars are captured before any rollback so a later read cannot become a
    # lazy refresh inside the event loop.
    question_id = question.id
    owner_id = session.owner_user_id
    session_id = session.id
    max_attempts = session.max_attempts
    explanation = question.explanation
    correct_answer = question.correct_answer
    question_type = question.type
    payload_hash = _hash({"question_id": str(question_id), "answer": answer})
    snapshot = {
        "type": question_type,
        "options": question.options,
        "items": question.items,
        "correct_answer": correct_answer,
        "correct_order": correct_answer if question_type == "ORDERING" else None,
    }

    # A replay of an already-recorded answer must return the stored verdict even
    # when the session has since completed: the client is retrying, not asking
    # to answer again.
    replay = await db.scalar(
        select(QuizAttempt).where(
            QuizAttempt.owner_user_id == owner_id,
            QuizAttempt.idempotency_key == idempotency_key,
        )
    )
    if replay is not None:
        if replay.payload_hash != payload_hash:
            await db.rollback()
            raise QuizRequestRejected("同一幂等键对应不同的作答内容", code="IDEMPOTENCY_CONFLICT")
        replay_outcome = replay.outcome
        replay_correct = replay.is_correct
        replay_no = replay.attempt_no
        replay_id = replay.id
        session_status_now = session.status
        # Read-only transaction: commit (not rollback) so the ORM objects the
        # caller still needs are not expired.
        await db.commit()
        used_total = int(
            await db.scalar(
                select(func.count())
                .select_from(QuizAttempt)
                .where(
                    QuizAttempt.question_id == question_id,
                    QuizAttempt.attempt_no.is_not(None),
                )
            )
            or 0
        )
        return AttemptOutcome(
            attempt_id=replay_id,
            outcome=replay_outcome,
            is_correct=replay_correct,
            attempt_no=replay_no,
            attempts_used=used_total,
            max_attempts=max_attempts,
            explanation=explanation,
            correct_answer=correct_answer,
            idempotent_replay=True,
            session_status=session_status_now,
        )

    if session.status != "ACTIVE":
        await db.rollback()
        raise QuizRequestRejected("测验已结束，不能再作答", code="SESSION_COMPLETED")

    try:
        result = score_answer(snapshot, answer)
    except ScoringUnavailable as exc:
        # System failure: recorded honestly, no attempt number, no wrong-answer
        # evidence, and the idempotency key stays free for a retry.
        failure = QuizAttempt(
            session_id=session_id,
            question_id=question_id,
            owner_user_id=owner_id,
            attempt_no=None,
            answer=answer,
            outcome="SYSTEM_FAILURE",
            is_correct=None,
            idempotency_key=f"{idempotency_key}#failure-{uuid.uuid4().hex[:8]}",
            payload_hash=payload_hash,
            failure_code=exc.code,
            scoring_version=session.scoring_version,
        )
        db.add(failure)
        await db.commit()
        raise QuizRequestRejected(
            f"判分服务暂时不可用（{exc.code}），本次不计为答错", code="SCORING_UNAVAILABLE"
        ) from exc
    except AnswerRejected as exc:
        # Client error: nothing was written, so no attempt was consumed.
        await db.rollback()
        raise QuizRequestRejected(exc.detail, code="INVALID_ANSWER") from exc

    used = int(
        await db.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(
                QuizAttempt.question_id == question.id,
                QuizAttempt.attempt_no.is_not(None),
            )
        )
        or 0
    )
    if used >= max_attempts:
        await db.rollback()
        raise QuizRequestRejected("本题作答次数已用完", code="ATTEMPT_LIMIT_REACHED")

    attempt_id = uuid.uuid4()
    statement = (
        pg_insert(QuizAttempt)
        .values(
            id=attempt_id,
            session_id=session_id,
            question_id=question_id,
            owner_user_id=owner_id,
            attempt_no=used + 1,
            answer=result.normalised_answer,
            outcome="CORRECT" if result.is_correct else "INCORRECT",
            is_correct=result.is_correct,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            scoring_version=session.scoring_version,
        )
        .on_conflict_do_nothing(index_elements=["owner_user_id", "idempotency_key"])
        .returning(QuizAttempt.id)
    )
    inserted = await db.scalar(statement)
    if inserted is None:
        # Replay or conflict: the attempt row already exists.
        existing = await db.scalar(
            select(QuizAttempt).where(
                QuizAttempt.owner_user_id == owner_id,
                QuizAttempt.idempotency_key == idempotency_key,
            )
        )
        await db.rollback()
        if existing is None:  # pragma: no cover - conflicting row vanished
            raise QuizRequestRejected("幂等键已被占用", code="IDEMPOTENCY_CONFLICT")
        if existing.payload_hash != payload_hash:
            raise QuizRequestRejected("同一幂等键对应不同的作答内容", code="IDEMPOTENCY_CONFLICT")
        used_total = int(
            await db.scalar(
                select(func.count())
                .select_from(QuizAttempt)
                .where(
                    QuizAttempt.question_id == question.id,
                    QuizAttempt.attempt_no.is_not(None),
                )
            )
            or 0
        )
        return AttemptOutcome(
            attempt_id=existing.id,
            outcome=existing.outcome,
            is_correct=existing.is_correct,
            attempt_no=existing.attempt_no,
            attempts_used=used_total,
            max_attempts=max_attempts,
            explanation=question.explanation,
            correct_answer=question.correct_answer,
            idempotent_replay=True,
            session_status=session.status,
        )

    _record_evidence(
        db,
        session=session,
        kind="QUIZ_ANSWERED",
        outcome="CORRECT" if result.is_correct else "INCORRECT",
        source_event_id=inserted,
        question=question,
    )
    if not result.is_correct:
        await _link_review(db, session=session, question=question)
    session.base_revision += 1

    if await _completed(db, session=session):
        session.status = "COMPLETED"
        session.completed_at = datetime.now(UTC)
        _record_evidence(
            db,
            session=session,
            kind="QUIZ_SESSION_COMPLETED",
            outcome="COMPLETED",
            source_event_id=session.id,
        )
    await db.commit()
    return AttemptOutcome(
        attempt_id=inserted,
        outcome="CORRECT" if result.is_correct else "INCORRECT",
        is_correct=result.is_correct,
        attempt_no=used + 1,
        attempts_used=used + 1,
        max_attempts=max_attempts,
        explanation=explanation,
        correct_answer=correct_answer,
        idempotent_replay=False,
        session_status=session.status,
    )


async def _link_review(db: AsyncSession, *, session: QuizSession, question: QuizQuestion) -> None:
    """Incorrect answer → review source, with an honest similar-source label."""

    similar = await db.scalar(
        select(QuizDraft)
        .join(User, User.id == QuizDraft.owner_user_id)
        .where(
            QuizDraft.chapter_id == session.chapter_id,
            QuizDraft.source_conversation_id == session.source_conversation_id,
            QuizDraft.status.in_(("HUMAN_APPROVED", "AUTO_VALIDATED")),
            QuizDraft.validation_passed.is_(True),
            QuizDraft.id != session.draft_id,
            or_(
                QuizDraft.owner_user_id == session.owner_user_id,
                User.role == UserRole.ADMIN.value,
            ),
        )
        .order_by(QuizDraft.created_at.desc())
        .limit(1)
    )
    similar_key = None
    if similar is not None and isinstance(similar.draft, dict):
        for candidate in similar.draft.get("questions", []):
            if candidate.get("objective_id") == question.objective_id:
                similar_key = candidate.get("question_key")
                break
        if similar_key is None:
            similar = None  # no same-objective question: do not pretend a match
    link = QuizReviewLink(
        session_id=session.id,
        question_id=question.id,
        owner_user_id=session.owner_user_id,
        objective_id=question.objective_id,
        reason="INCORRECT",
        similar_draft_id=similar.id if similar is not None else None,
        similar_question_key=similar_key,
        thresholds_version=session.thresholds_version,
    )
    db.add(link)
    await db.flush()
    _record_evidence(
        db,
        session=session,
        kind="QUIZ_REVIEW_LINKED",
        outcome="LINKED",
        source_event_id=link.id,
        question=question,
    )


async def request_hint(
    db: AsyncSession,
    *,
    session: QuizSession,
    question: QuizQuestion,
    level: int,
    idempotency_key: str,
) -> dict:
    await db.refresh(session, with_for_update=True)
    hint_texts = list(question.hints or [])
    question_id = question.id
    owner_id = session.owner_user_id
    limit = min(session.max_hints, len(hint_texts))
    payload_hash = _hash({"question_id": str(question_id), "level": level})

    replay = await db.scalar(
        select(QuizHintEvent).where(
            QuizHintEvent.owner_user_id == owner_id,
            QuizHintEvent.idempotency_key == idempotency_key,
        )
    )
    if replay is not None:
        if replay.payload_hash != payload_hash:
            await db.rollback()
            raise QuizRequestRejected("同一幂等键对应不同的提示请求", code="IDEMPOTENCY_CONFLICT")
        replay_level = replay.level
        await db.commit()
        used_now = int(
            await db.scalar(
                select(func.count())
                .select_from(QuizHintEvent)
                .where(QuizHintEvent.question_id == question_id)
            )
            or 0
        )
        return {
            "level": replay_level,
            "text": hint_texts[replay_level - 1],
            "hints_used": used_now,
            "hint_limit": limit,
            "idempotent_replay": True,
        }

    if session.status != "ACTIVE":
        await db.rollback()
        raise QuizRequestRejected("测验已结束，不能再取提示", code="SESSION_COMPLETED")

    used = int(
        await db.scalar(
            select(func.count())
            .select_from(QuizHintEvent)
            .where(QuizHintEvent.question_id == question_id)
        )
        or 0
    )

    if level < 1 or level > limit:
        await db.rollback()
        raise QuizRequestRejected("提示级数超出上限", code="HINT_LIMIT_REACHED")
    if level != used + 1:
        await db.rollback()
        raise QuizRequestRejected("提示必须按级释放", code="HINT_LEVEL_OUT_OF_ORDER")

    hint_id = uuid.uuid4()
    statement = (
        pg_insert(QuizHintEvent)
        .values(
            id=hint_id,
            session_id=session.id,
            question_id=question_id,
            owner_user_id=owner_id,
            level=level,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
        )
        .on_conflict_do_nothing(index_elements=["owner_user_id", "idempotency_key"])
        .returning(QuizHintEvent.id)
    )
    inserted = await db.scalar(statement)
    if inserted is None:
        existing = await db.scalar(
            select(QuizHintEvent).where(
                QuizHintEvent.owner_user_id == owner_id,
                QuizHintEvent.idempotency_key == idempotency_key,
            )
        )
        await db.rollback()
        if existing is None:  # pragma: no cover
            raise QuizRequestRejected("幂等键已被占用", code="IDEMPOTENCY_CONFLICT")
        if existing.payload_hash != payload_hash:
            raise QuizRequestRejected("同一幂等键对应不同的提示请求", code="IDEMPOTENCY_CONFLICT")
        return {
            "level": existing.level,
            "text": hint_texts[existing.level - 1],
            "hints_used": used,
            "hint_limit": limit,
            "idempotent_replay": True,
        }

    _record_evidence(
        db,
        session=session,
        kind="QUIZ_HINT_VIEWED",
        outcome="VIEWED",
        source_event_id=inserted,
        question=question,
    )
    session.base_revision += 1
    await db.commit()
    return {
        "level": level,
        "text": hint_texts[level - 1],
        "hints_used": used + 1,
        "hint_limit": limit,
        "idempotent_replay": False,
    }


async def review_overview(db: AsyncSession, *, session: QuizSession) -> dict:
    links = (
        await db.scalars(
            select(QuizReviewLink)
            .where(
                QuizReviewLink.session_id == session.id,
                QuizReviewLink.owner_user_id == session.owner_user_id,
            )
            .order_by(QuizReviewLink.created_at)
        )
    ).all()
    items = []
    for link in links:
        similar_label = None
        if link.similar_draft_id is not None:
            similar_label = (
                "AI 草稿（同目标，未审校）" if session.source_kind == "AI_DRAFT" else "人工审校题源"
            )
        items.append(
            {
                "question_id": str(link.question_id),
                "objective_id": link.objective_id,
                "reason": link.reason,
                "similar_source": {
                    "draft_id": str(link.similar_draft_id) if link.similar_draft_id else None,
                    "question_key": link.similar_question_key,
                    "label": similar_label,
                },
                "next_action": (
                    "REVIEW_SIMILAR_QUESTION"
                    if link.similar_draft_id is not None
                    else "REVIEW_SOURCE_MATERIAL"
                ),
                "thresholds_version": link.thresholds_version,
                "effect_verified": False,  # no claim of validated learning effect
            }
        )
    return {
        "session_id": str(session.id),
        "thresholds_version": session.thresholds_version,
        "scoring_version": session.scoring_version,
        "items": items,
        "notice": "复习建议依据本地真实作答证据；未经过教学效果官方验证。",
    }
