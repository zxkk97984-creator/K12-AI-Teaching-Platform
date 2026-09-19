"""Policy snapshot lifecycle and evidence bookkeeping (QA04/QA06)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import LearnerProfile
from app.modules.learning.models import (
    CORRECT_OUTCOMES,
    REAL_ACTIVITY_KINDS,
    LearningEvidence,
    LearningPolicySnapshot,
)
from app.modules.learning.policy import build_policy, evidence_level_from


async def evidence_counts(db: AsyncSession, session_id) -> tuple[int, int]:
    """(real activities, correct activities). Skips never count as evidence."""

    rows = (
        await db.execute(
            select(LearningEvidence.kind, LearningEvidence.outcome).where(
                LearningEvidence.session_id == session_id
            )
        )
    ).all()
    real = [row for row in rows if row[0] in REAL_ACTIVITY_KINDS]
    correct = [row for row in real if row[1] in CORRECT_OUTCOMES]
    return len(real), len(correct)


async def current_evidence_level(db: AsyncSession, session_id) -> str:
    real, correct = await evidence_counts(db, session_id)
    return evidence_level_from(real_activities=real, correct_activities=correct)


async def record_evidence(
    db: AsyncSession, *, session, kind: str, outcome: str, reference: str | None = None
) -> LearningEvidence:
    row = LearningEvidence(
        session_id=session.id,
        owner_user_id=session.owner_user_id,
        kind=kind,
        outcome=outcome,
        reference=reference,
    )
    db.add(row)
    await db.flush()
    return row


def _snapshot_key(snapshot: LearningPolicySnapshot) -> tuple:
    return (
        snapshot.stage,
        snapshot.grade,
        snapshot.preferred_style,
        snapshot.evidence_level,
        snapshot.input_revision,
    )


async def ensure_policy_snapshot(
    db: AsyncSession, *, session, profile: LearnerProfile | None
) -> tuple[LearningPolicySnapshot, bool]:
    """Return the current snapshot, creating a superseding one when inputs move.

    The snapshot is what downstream teaching consumes: a run bound to an older
    snapshot is rejected as STALE instead of writing feedback into a new policy.
    """

    level = await current_evidence_level(db, session.id)
    stage = (profile.stage if profile and profile.stage else session.stage) or session.stage
    grade = profile.grade if profile else session.grade
    preferred_style = profile.preferred_style if profile else "AUTO"
    revision = profile.revision if profile else 0
    proactive = profile.proactive_guidance_enabled if profile else True

    policy = build_policy(
        stage=stage,
        grade=grade,
        preferred_style=preferred_style,
        evidence_level=level,
        proactive_guidance_enabled=proactive,
    )
    snapshot = policy.to_snapshot()

    if session.policy_snapshot_id is not None:
        existing = await db.scalar(
            select(LearningPolicySnapshot).where(
                LearningPolicySnapshot.id == session.policy_snapshot_id
            )
        )
        if existing is not None and _snapshot_key(existing) == (
            stage,
            grade,
            preferred_style,
            level,
            revision,
        ):
            return existing, False

    now = datetime.now(UTC)
    if session.policy_snapshot_id is not None:
        previous = await db.scalar(
            select(LearningPolicySnapshot).where(
                LearningPolicySnapshot.id == session.policy_snapshot_id
            )
        )
        if previous is not None:
            previous.superseded_at = now

    row = LearningPolicySnapshot(
        session_id=session.id,
        owner_user_id=session.owner_user_id,
        stage=stage,
        grade=grade,
        preferred_style=preferred_style,
        evidence_level=level,
        input_revision=revision,
        policy=snapshot,
    )
    db.add(row)
    await db.flush()
    session.policy_snapshot_id = row.id
    session.stage = stage
    session.grade = grade
    return row, True


async def snapshot_for(db: AsyncSession, snapshot_id) -> LearningPolicySnapshot | None:
    return await db.scalar(
        select(LearningPolicySnapshot).where(LearningPolicySnapshot.id == snapshot_id)
    )


async def evidence_summary(db: AsyncSession, session_id) -> dict:
    real, correct = await evidence_counts(db, session_id)
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(LearningEvidence)
            .where(LearningEvidence.session_id == session_id)
        )
        or 0
    )
    skipped = int(
        await db.scalar(
            select(func.count())
            .select_from(LearningEvidence)
            .where(
                LearningEvidence.session_id == session_id,
                LearningEvidence.kind == "ACTIVITY_SKIPPED",
            )
        )
        or 0
    )
    return {
        "total": total,
        "real_activities": real,
        "correct_activities": correct,
        "skipped": skipped,
        "evidence_level": evidence_level_from(real_activities=real, correct_activities=correct),
    }
