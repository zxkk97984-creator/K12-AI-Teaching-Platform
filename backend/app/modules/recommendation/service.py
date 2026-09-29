"""Recommendation service: assemble inputs, project on events, read cheaply (T19).

Read path (``compute_next_step``): pure computation over the current facts plus
one SELECT of the latest snapshot. It never inserts, updates or deletes anything,
so ten consecutive GETs cannot create a single business row.

Write path (``refresh_snapshot``): called by an event (a tutor run) or by an
explicit CSRF-protected refresh. Identical inputs reuse the stored snapshot;
changed inputs create a new ``source_revision`` and supersede the old one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.assessment.models import QuizSession
from app.modules.content.models import ChapterReviewState
from app.modules.content.service import viewer_scope_from_profile, visible_chapters
from app.modules.identity.models import LearnerProfile
from app.modules.learning.models import CORRECT_OUTCOMES, EvidenceItem, Observation
from app.modules.learning.projection import needs_projection as evidence_needs_projection
from app.modules.learning.projection import project_and_observe
from app.modules.memory.service import derive_candidates, memory_context
from app.modules.recommendation.decision import (
    RULE_VERSION,
    THRESHOLDS_VERSION,
    CandidateChapter,
    DecisionInputs,
    LessonState,
    ObjectiveState,
    decide_next_step,
    inputs_hash,
)
from app.modules.recommendation.models import (
    RecommendationFeedback,
    RecommendationFeedbackEvent,
    RecommendationSnapshot,
)
from app.modules.teaching.models import LessonSession

HINT_OR_SKIP_KINDS = ("QUIZ_HINT_VIEWED", "LESSON_ACTIVITY", "QUIZ_REVIEW_LINKED")


class FeedbackRevisionConflict(Exception):
    """Stale or conflicting feedback write; nothing was changed."""


class FeedbackNotFound(Exception):
    """No feedback row for this subject (another owner's row is invisible)."""


async def _valid_evidence(
    db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int
) -> list[EvidenceItem]:
    """Evidence whose backend source is still usable (withdrawn sources drop out)."""

    items = list(
        await db.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.owner_user_id == owner_user_id)
            .order_by(EvidenceItem.observed_at.desc())
            .limit(limit)
        )
    )
    quiz_session_ids: set[uuid.UUID] = set()
    for item in items:
        raw = (item.source_ref or {}).get("quiz_session_id")
        if isinstance(raw, str):
            try:
                quiz_session_ids.add(uuid.UUID(raw))
            except ValueError:  # pragma: no cover - defensive
                continue
    if not quiz_session_ids:
        return items
    withdrawn_rows = (
        await db.execute(
            select(QuizSession.id)
            .join(ChapterReviewState, ChapterReviewState.revision_id == QuizSession.revision_id)
            .where(
                QuizSession.id.in_(quiz_session_ids),
                ChapterReviewState.publication_status == "WITHDRAWN",
            )
        )
    ).all()
    withdrawn = {row[0] for row in withdrawn_rows}
    if not withdrawn:
        return items
    valid: list[EvidenceItem] = []
    for item in items:
        raw = (item.source_ref or {}).get("quiz_session_id")
        try:
            session_id = uuid.UUID(raw) if isinstance(raw, str) else None
        except ValueError:  # pragma: no cover - defensive
            session_id = None
        if session_id in withdrawn:
            continue
        valid.append(item)
    return valid


async def assemble_inputs(
    db: AsyncSession, *, owner_user_id: uuid.UUID, settings: Settings
) -> DecisionInputs:
    profile = await db.scalar(select(LearnerProfile).where(LearnerProfile.user_id == owner_user_id))
    stage = profile.stage if profile and profile.stage else None
    if stage is None:
        return DecisionInputs(stage="UNKNOWN", grade=None, preferred_style="AUTO", real_answers=0)

    lesson_row = await db.scalar(
        select(LessonSession)
        .where(
            LessonSession.owner_user_id == owner_user_id,
            LessonSession.lifecycle.in_(("ACTIVE", "PAUSED")),
            LessonSession.phase != "COMPLETED",
        )
        .order_by(LessonSession.updated_at.desc())
        .limit(1)
    )
    active_lesson = None
    if lesson_row is not None:
        chapter_title = str((lesson_row.context or {}).get("chapter", {}).get("title") or "这一节")
        active_lesson = LessonState(
            session_id=str(lesson_row.id),
            chapter_id=str(lesson_row.chapter_id),
            chapter_title=chapter_title,
            phase=lesson_row.phase,
            lifecycle=lesson_row.lifecycle,
            policy_snapshot_id=(
                str(lesson_row.policy_snapshot_id) if lesson_row.policy_snapshot_id else None
            ),
        )

    items = await _valid_evidence(
        db, owner_user_id=owner_user_id, limit=settings.recommendation_evidence_limit
    )
    answers = [item for item in items if item.source_kind == "QUIZ_ANSWERED"]
    observation_rows = list(
        await db.scalars(
            select(Observation).where(
                Observation.owner_user_id == owner_user_id, Observation.superseded_at.is_(None)
            )
        )
    )
    level_by_objective = {row.subject_key: row.level for row in observation_rows}
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in answers:
        if item.objective_id:
            grouped.setdefault(item.objective_id, []).append(item)
    objectives = tuple(
        ObjectiveState(
            objective_id=objective,
            answered=len(rows),
            incorrect=len([row for row in rows if row.outcome not in CORRECT_OUTCOMES]),
            level=level_by_objective.get(objective, "EMERGING"),
            last_incorrect_evidence_id=next(
                (
                    str(row.id)
                    for row in sorted(rows, key=lambda entry: entry.observed_at, reverse=True)
                    if row.outcome not in CORRECT_OUTCOMES
                ),
                None,
            ),
            evidence_ids=tuple(str(row.id) for row in rows),
        )
        for objective, rows in sorted(grouped.items())
    )

    viewer = viewer_scope_from_profile(profile, settings)
    catalogue = await visible_chapters(db, viewer)
    candidates = tuple(
        CandidateChapter(
            chapter_id=str(row.chapter_id),
            title=row.title,
            course_title=row.course_title,
            order_index=row.order_index,
            stage=row.stage.value if hasattr(row.stage, "value") else str(row.stage),
            knowledge_point_slugs=(),
        )
        for row in catalogue
    )

    completed_rows = (
        await db.scalars(
            select(LessonSession.chapter_id).where(
                LessonSession.owner_user_id == owner_user_id,
                LessonSession.lifecycle == "COMPLETED",
                LessonSession.chapter_id.is_not(None),
            )
        )
    ).all()
    completed = tuple(sorted({str(chapter_id) for chapter_id in completed_rows}))

    memories = await memory_context(
        db, owner_user_id=owner_user_id, limit=settings.recommendation_memory_limit
    )
    ignored_rows = (
        await db.scalars(
            select(RecommendationFeedback.subject_key).where(
                RecommendationFeedback.owner_user_id == owner_user_id,
                RecommendationFeedback.state == "IGNORED",
            )
        )
    ).all()

    real_answers = len(answers)
    activity_items = [item for item in items if item.source_kind in HINT_OR_SKIP_KINDS]
    return DecisionInputs(
        stage=stage,
        grade=profile.grade if profile else None,
        preferred_style=profile.preferred_style if profile else "AUTO",
        interests=tuple(profile.interests or []) if profile else (),
        active_lesson=active_lesson,
        objectives=objectives,
        candidates=candidates,
        completed_chapter_ids=completed,
        active_memory_ids=tuple(item["id"] for item in memories),
        real_answers=real_answers,
        hints_or_skips_only=real_answers == 0 and bool(activity_items),
        ignored_subjects=tuple(sorted(str(key) for key in ignored_rows)),
        evidence_ids=tuple(str(item.id) for item in items),
    )


def _snapshot_dto(row: RecommendationSnapshot) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "source_revision": row.source_revision,
        "rule_version": row.rule_version,
        "thresholds_version": row.thresholds_version,
        "primary": dict(row.primary_item or {}),
        "alternatives": list(row.alternatives or []),
        "basis": dict(row.basis or {}),
        "inputs_hash": row.inputs_hash,
        "effect_verified": row.effect_verified,
        "created_at": row.created_at.isoformat(),
        "superseded_at": row.superseded_at.isoformat() if row.superseded_at else None,
    }


async def latest_snapshot(db: AsyncSession, *, owner_user_id: uuid.UUID):
    return await db.scalar(
        select(RecommendationSnapshot)
        .where(RecommendationSnapshot.owner_user_id == owner_user_id)
        .order_by(RecommendationSnapshot.source_revision.desc())
        .limit(1)
    )


async def compute_next_step(
    db: AsyncSession, *, owner_user_id: uuid.UUID, settings: Settings
) -> dict[str, Any]:
    """Read-only: pure decision + one SELECT (never writes)."""

    inputs = await assemble_inputs(db, owner_user_id=owner_user_id, settings=settings)
    decision = decide_next_step(inputs)
    digest = inputs_hash(inputs)
    stored = await latest_snapshot(db, owner_user_id=owner_user_id)
    pending_projection = await evidence_needs_projection(
        db, owner_user_id=owner_user_id, limit=settings.recommendation_evidence_limit
    )
    if stored is None:
        snapshot_state = "NOT_PROJECTED"
    elif stored.inputs_hash == digest:
        snapshot_state = "CURRENT"
    else:
        snapshot_state = "STALE"
    return {
        "primary": decision["primary"],
        "alternatives": decision["alternatives"],
        "basis": decision["basis"],
        "rule_version": RULE_VERSION,
        "thresholds_version": THRESHOLDS_VERSION,
        "effect_verified": False,
        "honest_notes": decision["honest_notes"],
        "inputs_hash": digest,
        "snapshot_state": snapshot_state,
        # A trusted event that has not been projected yet is reported honestly
        # instead of silently showing an older picture.
        "needs_projection": pending_projection,
        "needs_refresh": snapshot_state != "CURRENT" or pending_projection,
        "snapshot": _snapshot_dto(stored) if stored is not None else None,
        "ignored_subjects": list(inputs.ignored_subjects),
        "cold_start": inputs.real_answers == 0,
    }


async def refresh_snapshot(
    db: AsyncSession, *, owner_user_id: uuid.UUID, settings: Settings
) -> dict[str, Any]:
    """Event-driven projection: project the evidence, then store the decision.

    This is the only place that projects on the recommendation path (the read
    path never writes): a tutor run or an explicit refresh is an event, and the
    projection itself is deduplicated in T18's store.
    """

    await project_and_observe(
        db, owner_user_id=owner_user_id, limit=settings.recommendation_evidence_limit
    )
    await derive_candidates(
        db, owner_user_id=owner_user_id, limit=settings.recommendation_evidence_limit
    )
    inputs = await assemble_inputs(db, owner_user_id=owner_user_id, settings=settings)
    decision = decide_next_step(inputs)
    digest = inputs_hash(inputs)
    existing = await db.scalar(
        select(RecommendationSnapshot).where(
            RecommendationSnapshot.owner_user_id == owner_user_id,
            RecommendationSnapshot.inputs_hash == digest,
        )
    )
    created = False
    row = existing
    if existing is None:
        next_revision = (
            int(
                await db.scalar(
                    select(
                        func.coalesce(func.max(RecommendationSnapshot.source_revision), 0)
                    ).where(RecommendationSnapshot.owner_user_id == owner_user_id)
                )
                or 0
            )
            + 1
        )
        previous = await latest_snapshot(db, owner_user_id=owner_user_id)
        if previous is not None:
            previous.superseded_at = datetime.now(UTC)
        statement = (
            pg_insert(RecommendationSnapshot)
            .values(
                id=uuid.uuid4(),
                owner_user_id=owner_user_id,
                source_revision=next_revision,
                rule_version=RULE_VERSION,
                thresholds_version=THRESHOLDS_VERSION,
                primary_item=decision["primary"],
                alternatives=decision["alternatives"],
                basis=decision["basis"],
                inputs_hash=digest,
                effect_verified=False,
            )
            .on_conflict_do_nothing(index_elements=["owner_user_id", "inputs_hash"])
            .returning(RecommendationSnapshot.id)
        )
        inserted = await db.scalar(statement)
        if inserted is None:  # concurrent writer with identical inputs
            row = await db.scalar(
                select(RecommendationSnapshot).where(
                    RecommendationSnapshot.owner_user_id == owner_user_id,
                    RecommendationSnapshot.inputs_hash == digest,
                )
            )
        else:
            created = True
            row = await db.scalar(
                select(RecommendationSnapshot).where(RecommendationSnapshot.id == inserted)
            )
    await db.commit()
    return {
        "created": created,
        "inputs_hash": digest,
        "snapshot": _snapshot_dto(row) if row is not None else None,
    }


async def snapshot_detail(
    db: AsyncSession, *, owner_user_id: uuid.UUID, snapshot_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await db.scalar(
        select(RecommendationSnapshot).where(
            RecommendationSnapshot.id == snapshot_id,
            RecommendationSnapshot.owner_user_id == owner_user_id,
        )
    )
    if row is None:
        return None
    body = _snapshot_dto(row)
    body["trace"] = {
        "evidence_ids": list(dict(row.basis or {}).get("evidence_ids", [])),
        "active_memory_ids": list(dict(row.basis or {}).get("active_memory_ids", [])),
        "rule_version": row.rule_version,
        "thresholds_version": row.thresholds_version,
    }
    return body


async def list_feedback(db: AsyncSession, *, owner_user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(RecommendationFeedback)
            .where(RecommendationFeedback.owner_user_id == owner_user_id)
            .order_by(RecommendationFeedback.updated_at.desc())
        )
    ).all()
    return [
        {
            "subject_key": row.subject_key,
            "state": row.state,
            "revision": row.revision,
            "reason": row.reason,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


async def apply_feedback(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    subject_key: str,
    action: str,
    base_revision: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """IGNORE/RESTORE one subject; stale base_revision is rejected atomically."""

    if action not in ("IGNORE", "RESTORE"):
        raise FeedbackRevisionConflict("不支持的推荐操作")
    row = await db.scalar(
        select(RecommendationFeedback)
        .where(
            RecommendationFeedback.owner_user_id == owner_user_id,
            RecommendationFeedback.subject_key == subject_key,
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if row is None:
        if base_revision != 0:
            await db.rollback()
            raise FeedbackRevisionConflict("推荐状态已被更新，请刷新后重试")
        state = "IGNORED" if action == "IGNORE" else "ACTIVE"
        row = RecommendationFeedback(
            owner_user_id=owner_user_id,
            subject_key=subject_key,
            state=state,
            revision=1,
            reason=reason,
        )
        db.add(row)
        await db.flush()
        db.add(
            RecommendationFeedbackEvent(
                feedback_id=row.id,
                owner_user_id=owner_user_id,
                action=action,
                from_state="NONE",
                to_state=state,
                from_revision=0,
                to_revision=1,
                reason=reason,
            )
        )
        await db.commit()
        await db.refresh(row)
    else:
        if row.revision != base_revision:
            await db.rollback()
            raise FeedbackRevisionConflict("推荐状态已被更新，请刷新后重试")
        target_state = "IGNORED" if action == "IGNORE" else "ACTIVE"
        if row.state == target_state:
            # Idempotent: repeating the same action adds no revision and no event.
            await db.commit()
            await db.refresh(row)
        else:
            from_state = row.state
            from_revision = row.revision
            row.state = target_state
            row.revision = from_revision + 1
            row.reason = reason
            row.updated_at = now
            db.add(
                RecommendationFeedbackEvent(
                    feedback_id=row.id,
                    owner_user_id=owner_user_id,
                    action=action,
                    from_state=from_state,
                    to_state=target_state,
                    from_revision=from_revision,
                    to_revision=row.revision,
                    reason=reason,
                )
            )
            await db.commit()
            await db.refresh(row)

    events = (
        await db.scalars(
            select(RecommendationFeedbackEvent)
            .where(RecommendationFeedbackEvent.feedback_id == row.id)
            .order_by(RecommendationFeedbackEvent.created_at)
        )
    ).all()
    return {
        "subject_key": row.subject_key,
        "state": row.state,
        "revision": row.revision,
        "reason": row.reason,
        "updated_at": row.updated_at.isoformat(),
        "history": [
            {
                "id": str(event.id),
                "action": event.action,
                "from_state": event.from_state,
                "to_state": event.to_state,
                "from_revision": event.from_revision,
                "to_revision": event.to_revision,
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }
