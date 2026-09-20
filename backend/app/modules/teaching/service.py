"""Conversation/run service: short transactions, DB idempotency, leases.

The sequencing that matters (E1/E2):

1. ``create_turn`` commits the user message, the run row and the run's claim
   state in one short transaction, then returns. It never talks to the gateway.
2. ``acquire_lease`` claims a QUEUED run with a lease token; the caller may then
   invoke the gateway *after* that transaction has committed.
3. ``finalize_run`` re-checks the lease token, the deadline and the cancel flag
   before writing anything. A late worker can only downgrade a RUNNING run to
   STALE; it can never overwrite a newer terminal state.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.content.models import Chapter, ChapterRevision, Release
from app.modules.content.service import viewer_scope_from_profile, visible_chapter_detail
from app.modules.identity.models import LearnerProfile, User
from app.modules.learning.models import LearningEvidence  # noqa: F401  (schema import parity)
from app.modules.learning.service import (
    ensure_policy_snapshot,
    evidence_counts,
    evidence_summary,
    record_evidence,
)
from app.modules.resources.animation_service import visible_animations
from app.modules.resources.service import authorized_resource_ids_for_teaching
from app.modules.teaching.context import build_session_context, load_fixture_allowance
from app.modules.teaching.models import (
    TERMINAL_RUN_STATUSES,
    AgentRun,
    ConversationMessage,
    LessonSession,
    MessageRole,
    RemoteBinding,
    RunStatus,
    TeachingPhaseEvent,
)
from app.modules.teaching.phase import (
    IllegitimateTransition,
    LessonEvent,
    Lifecycle,
    Phase,
    apply_phase_suggestion,  # noqa: F401  (re-exported for callers/tests)
    completion_allowed,
    resolve_event,
)
from app.modules.teaching.schemas import (
    MessageDTO,
    RunDTO,
    SessionDetail,
    SessionSummary,
)


class SessionNotVisible(Exception):
    """The chapter is not readable by this student in this runtime."""


class RunConflict(Exception):
    """Same idempotency key with a different request body."""


def request_hash(*, operation: str, message: str) -> str:
    canonical = f"{operation}\x00{message}".encode()
    return hashlib.sha256(canonical).hexdigest()


async def create_session(
    db: AsyncSession,
    *,
    settings: Settings,
    user: User,
    chapter_id: uuid.UUID,
) -> LessonSession:
    profile = await db.scalar(select(LearnerProfile).where(LearnerProfile.user_id == user.id))
    viewer = viewer_scope_from_profile(profile, settings)
    detail = await visible_chapter_detail(db, chapter_id=chapter_id, viewer=viewer)
    if detail is None:
        raise SessionNotVisible("chapter is not visible to this student")

    chapter = await db.scalar(select(Chapter).where(Chapter.id == chapter_id))
    revision = await db.scalar(
        select(ChapterRevision).where(
            ChapterRevision.chapter_id == chapter_id,
            ChapterRevision.revision == detail.revision,
        )
    )
    release = await db.scalar(select(Release).where(Release.id == revision.release_id))
    if chapter is None or revision is None or release is None:  # pragma: no cover - FK guarantees
        raise SessionNotVisible("chapter revision is incomplete")

    context = build_session_context(
        chapter_slug=chapter.stable_slug,
        chapter_id=str(chapter.id),
        chapter_title=chapter.title,
        revision_number=revision.revision,
        revision_id=str(revision.id),
        stage=revision.stage,
        objectives=list(revision.objectives or []),
        blocks=list(revision.body or []),
    )
    context["allowed_resource_ids"] = await authorized_resource_ids_for_teaching(
        db, revision_id=revision.id, viewer=viewer
    )
    context["allowed_animation_ids"] = [
        entry["id"] for entry in await visible_animations(db, viewer=viewer)
    ]
    allowance = None
    if settings.gateway_mode == "fixture" and release.is_test_fixture:
        allowance = load_fixture_allowance()

    session = LessonSession(
        owner_user_id=user.id,
        chapter_id=chapter.id,
        revision_id=revision.id,
        curriculum_revision=context["curriculum_revision"],
        stage=revision.stage,
        grade=profile.grade if profile else None,
        base_revision=0,
        context=context,
        fixture_allowance=allowance,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Chapter switch (F8/F10): the student left other lessons behind. Their
    # in-flight turns must not surface later as if they belonged to the new
    # chapter. Progress (phase/lifecycle) is preserved so the old lesson can
    # still be resumed; only the pending runs go STALE.
    others = (
        await db.scalars(
            select(LessonSession.id).where(
                LessonSession.owner_user_id == user.id,
                LessonSession.chapter_id != chapter.id,
            )
        )
    ).all()
    for other_id in others:
        await stale_pending_runs(db, session_id=other_id, reason="CHAPTER_SWITCH")
    await db.commit()
    return session


async def list_sessions(db: AsyncSession, *, user: User, limit: int = 20) -> list[SessionSummary]:
    rows = (
        await db.execute(
            select(
                LessonSession,
                Chapter.title,
                func.count(ConversationMessage.id),
                func.max(ConversationMessage.created_at),
            )
            .join(Chapter, Chapter.id == LessonSession.chapter_id)
            .outerjoin(ConversationMessage, ConversationMessage.session_id == LessonSession.id)
            .where(LessonSession.owner_user_id == user.id)
            .group_by(LessonSession.id, Chapter.title)
            .order_by(LessonSession.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        SessionSummary(
            id=session.id,
            chapter_id=session.chapter_id,
            chapter_title=title,
            curriculum_revision=session.curriculum_revision,
            stage=session.stage,
            grade=session.grade,
            base_revision=session.base_revision,
            created_at=session.created_at,
            message_count=count,
            last_message_at=last,
        )
        for session, title, count, last in rows
    ]


async def get_session_detail(
    db: AsyncSession, *, user: User, session_id: uuid.UUID
) -> SessionDetail | None:
    session = await db.scalar(
        select(LessonSession).where(
            LessonSession.id == session_id, LessonSession.owner_user_id == user.id
        )
    )
    if session is None:
        return None
    title = await db.scalar(select(Chapter.title).where(Chapter.id == session.chapter_id))
    messages = (
        await db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session.id)
            .order_by(ConversationMessage.created_at, ConversationMessage.id)
        )
    ).all()
    summary = SessionSummary(
        id=session.id,
        chapter_id=session.chapter_id,
        chapter_title=title or "",
        curriculum_revision=session.curriculum_revision,
        stage=session.stage,
        grade=session.grade,
        base_revision=session.base_revision,
        created_at=session.created_at,
        message_count=len(messages),
        last_message_at=messages[-1].created_at if messages else None,
    )
    return SessionDetail(
        **summary.model_dump(),
        messages=[
            MessageDTO(
                id=message.id,
                role=message.role,
                content_markdown=message.content_markdown,
                card=message.card,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


async def create_turn(
    db: AsyncSession,
    *,
    user: User,
    session: LessonSession,
    operation: str,
    message: str,
    idempotency_key: str,
) -> tuple[AgentRun, bool]:
    """Short transaction: user message + run + claim state, then return.

    Idempotency is decided by the database (``INSERT ... ON CONFLICT DO
    NOTHING``), so two concurrent tabs - or two API processes - cannot create
    two effective runs. The losing request writes nothing and replays the
    existing run.
    """

    digest = request_hash(operation=operation, message=message)
    run_id = uuid.uuid4()
    statement = (
        pg_insert(AgentRun)
        .values(
            id=run_id,
            session_id=session.id,
            owner_user_id=user.id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_hash=digest,
            status=RunStatus.QUEUED.value,
            attempt=1,
        )
        .on_conflict_do_nothing(index_elements=["owner_user_id", "idempotency_key"])
        .returning(AgentRun.id)
    )
    inserted_id = await db.scalar(statement)
    if inserted_id is not None:
        db.add(
            ConversationMessage(
                session_id=session.id,
                owner_user_id=user.id,
                run_id=inserted_id,
                role=MessageRole.USER.value,
                content_markdown=message,
                card=None,
            )
        )
        await db.commit()
        run = await db.scalar(select(AgentRun).where(AgentRun.id == inserted_id))
        if run is None:  # pragma: no cover - freshly inserted row
            raise RuntimeError("run vanished after insert")
        return run, True

    existing_id = await db.scalar(
        select(AgentRun.id).where(
            AgentRun.owner_user_id == user.id,
            AgentRun.idempotency_key == idempotency_key,
        )
    )
    await db.rollback()
    if existing_id is None:  # pragma: no cover - conflicting row deleted concurrently
        raise RunConflict("idempotency key is claimed by a vanished run")
    existing = await db.scalar(select(AgentRun).where(AgentRun.id == existing_id))
    if existing is None:  # pragma: no cover
        raise RunConflict("idempotency key is claimed by a vanished run")
    if existing.request_hash != digest:
        raise RunConflict("idempotency key reused with a different request body")
    return existing, False


async def get_run(db: AsyncSession, *, user: User, run_id: uuid.UUID) -> AgentRun | None:
    return await db.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_user_id == user.id)
    )


async def run_dto(db: AsyncSession, run: AgentRun, *, replay: bool = False) -> RunDTO:
    card = None
    if run.result_message_id is not None:
        card = await db.scalar(
            select(ConversationMessage.card).where(ConversationMessage.id == run.result_message_id)
        )
    binding_kind = await db.scalar(
        select(RemoteBinding.remote_kind).where(RemoteBinding.run_id == run.id)
    )
    return RunDTO(
        id=run.id,
        session_id=run.session_id,
        operation=run.operation,
        status=run.status,
        attempt=run.attempt,
        fixture=binding_kind == "FIXTURE" or (card or {}).get("fixture") is True,
        error_category=run.error_category,
        stale_reason=run.stale_reason,
        card=card,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        idempotent_replay=replay,
    )


async def acquire_lease(
    db: AsyncSession, *, run_id: uuid.UUID, ttl_seconds: int
) -> uuid.UUID | None:
    """Claim a QUEUED run. Returns the lease token, or None if already claimed."""

    token = uuid.uuid4()
    now = datetime.now(UTC)
    run = await db.scalar(
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None or run.status != RunStatus.QUEUED.value:
        await db.rollback()
        return None
    run.status = RunStatus.RUNNING.value
    run.lease_token = token
    run.lease_expires_at = now + timedelta(seconds=ttl_seconds)
    run.started_at = run.started_at or now
    await db.commit()
    return token


async def record_binding(
    db: AsyncSession,
    *,
    run: AgentRun,
    remote_kind: str,
    remote_id: str,
    remote_scope: str | None = None,
    remote_metadata: dict[str, Any] | None = None,
) -> None:
    existing = await db.scalar(select(RemoteBinding).where(RemoteBinding.run_id == run.id))
    if existing is None:
        db.add(
            RemoteBinding(
                run_id=run.id,
                owner_user_id=run.owner_user_id,
                remote_kind=remote_kind,
                remote_id=remote_id,
                remote_scope=remote_scope,
                remote_metadata=remote_metadata,
            )
        )
        await db.commit()


async def reusable_remote_conversation(
    db: AsyncSession,
    *,
    run: AgentRun,
    remote_scope: str,
) -> str | None:
    """Return only a successful same-owner/session/target Knodo binding."""

    return await db.scalar(
        select(RemoteBinding.remote_id)
        .join(AgentRun, AgentRun.id == RemoteBinding.run_id)
        .where(
            RemoteBinding.run_id != run.id,
            RemoteBinding.owner_user_id == run.owner_user_id,
            RemoteBinding.remote_kind == "KNODO",
            RemoteBinding.remote_scope == remote_scope,
            AgentRun.owner_user_id == run.owner_user_id,
            AgentRun.session_id == run.session_id,
            AgentRun.status == RunStatus.SUCCEEDED.value,
        )
        .order_by(AgentRun.completed_at.desc().nullslast(), RemoteBinding.created_at.desc())
        .limit(1)
    )


async def finalize_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    lease_token: uuid.UUID,
    error_category: str | None = None,
    assistant: dict[str, Any] | None = None,
    gateway_invocation_id: str | None = None,
) -> str:
    """Lease-guarded terminal transition. Returns the resulting run status."""

    now = datetime.now(UTC)
    run = await db.scalar(
        select(AgentRun)
        .where(AgentRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is not None and sa_inspect(run).expired:
        await db.refresh(run)
    if run is None:
        await db.rollback()
        return "MISSING"
    if run.status != RunStatus.RUNNING.value:
        status = run.status  # read before rollback expires the instance
        await db.rollback()
        return status
    if gateway_invocation_id is not None:
        run.gateway_invocation_id = gateway_invocation_id
    if (
        run.lease_token != lease_token
        or run.lease_expires_at is None
        or run.lease_expires_at <= now
    ):
        run.status = RunStatus.STALE.value
        run.stale_reason = "LEASE_EXPIRED"
        run.completed_at = now
        await db.commit()
        return RunStatus.STALE.value
    if run.cancel_requested_at is not None:
        run.status = RunStatus.CANCELLED.value
        run.completed_at = now
        run.lease_token = None
        await db.commit()
        return RunStatus.CANCELLED.value
    session_row = await db.scalar(
        select(LessonSession).where(LessonSession.id == run.session_id).with_for_update()
    )
    if (
        session_row is not None
        and run.policy_snapshot_id is not None
        and session_row.policy_snapshot_id != run.policy_snapshot_id
    ):
        # The policy changed (stage/grade/preferences/evidence): the late answer
        # must not be written into the new teaching state.
        run.status = RunStatus.STALE.value
        run.stale_reason = "POLICY_CHANGED"
        run.completed_at = now
        run.lease_token = None
        await db.commit()
        return RunStatus.STALE.value
    if error_category is not None or assistant is None:
        run.status = RunStatus.FAILED.value
        run.error_category = error_category or "UNKNOWN"
        run.completed_at = now
        run.lease_token = None
        await db.commit()
        return RunStatus.FAILED.value

    message = ConversationMessage(
        session_id=run.session_id,
        owner_user_id=run.owner_user_id,
        run_id=run.id,
        role=MessageRole.ASSISTANT.value,
        content_markdown=assistant["message_markdown"],
        card=assistant,
    )
    db.add(message)
    await db.flush()
    run.status = RunStatus.SUCCEEDED.value
    run.result_message_id = message.id
    run.completed_at = now
    run.lease_token = None
    session = await db.scalar(
        select(LessonSession).where(LessonSession.id == run.session_id).with_for_update()
    )
    if session is not None:
        session.base_revision = session.base_revision + 1
    await db.commit()
    return RunStatus.SUCCEEDED.value


async def request_cancel(db: AsyncSession, *, user: User, run_id: uuid.UUID) -> AgentRun | None:
    run = await db.scalar(
        select(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.owner_user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is not None and sa_inspect(run).expired:
        await db.refresh(run)
    if run is None:
        await db.rollback()
        return None
    if run.status in TERMINAL_RUN_STATUSES:
        status = run.status
        await db.rollback()
        run = await db.scalar(
            select(AgentRun).where(AgentRun.id == run_id).execution_options(populate_existing=True)
        )
        if run is None:  # pragma: no cover - row disappeared between the two reads
            raise RuntimeError("run vanished")
        run.status = status
        return run
    now = datetime.now(UTC)
    run.cancel_requested_at = run.cancel_requested_at or now
    if run.status == RunStatus.QUEUED.value:
        run.status = RunStatus.CANCELLED.value
        run.completed_at = now
    await db.commit()
    await db.refresh(run)
    return run


async def recover_expired_runs(db: AsyncSession) -> int:
    """Startup recovery: never re-invoke; record the honest uncertain state."""

    now = datetime.now(UTC)
    runs = (
        await db.scalars(
            select(AgentRun).where(
                AgentRun.status == RunStatus.RUNNING.value,
                AgentRun.lease_expires_at.is_not(None),
                AgentRun.lease_expires_at < now,
            )
        )
    ).all()
    for run in runs:
        run.lease_token = None
        run.completed_at = now
        if run.cancel_requested_at is not None:
            run.status = RunStatus.CANCELLED.value
        else:
            run.status = RunStatus.STALE.value
            run.stale_reason = "RECOVERED_AFTER_RESTART"
    if runs:
        await db.commit()
    return len(runs)


async def cancel_event_requested(db: AsyncSession, run_id: uuid.UUID) -> bool:
    value = await db.scalar(select(AgentRun.cancel_requested_at).where(AgentRun.id == run_id))
    return value is not None


# --------------------------------------------------------------------------- #
# T14: lesson phase/lifecycle, policy snapshots and idempotent opening
# --------------------------------------------------------------------------- #


class SessionBindingStale(Exception):
    """The lesson binding moved (chapter revision/stage): no further writes."""


async def ensure_session_binding(
    db: AsyncSession,
    *,
    settings: Settings,
    session: LessonSession,
    profile: LearnerProfile | None,
) -> None:
    """Refuse to advance a lesson whose chapter revision is no longer visible.

    A session is bound to one chapter revision (and to the student's stage via
    the viewer scope). When the released revision or the stage moves, the old
    lesson is marked STALE and its pending runs lose: late tutor output can
    never be written into the new lesson state.
    """

    if session.lifecycle == Lifecycle.STALE.value:
        raise SessionBindingStale("STALE")
    viewer = viewer_scope_from_profile(profile, settings)
    detail = await visible_chapter_detail(db, chapter_id=session.chapter_id, viewer=viewer)
    if detail is None:
        # Stage moved (or the revision was withdrawn): the learner's current
        # scope no longer contains this lesson.
        await mark_session_stale(db, session=session, reason="SESSION_BINDING_LOST")
        raise SessionBindingStale("SESSION_BINDING_LOST")
    if detail.revision_id != session.revision_id:
        await mark_session_stale(db, session=session, reason="CONTENT_REVISION_CHANGED")
        raise SessionBindingStale("CONTENT_REVISION_CHANGED")


class CompletionNotAllowed(Exception):
    """Completion was requested without any real learning activity."""


class LessonEventRejected(Exception):
    """The local event is not legal for the current phase/lifecycle."""


async def load_phase_state(session: LessonSession) -> tuple[Phase, Lifecycle, int]:
    return (
        Phase(session.phase),
        Lifecycle(session.lifecycle),
        session.phase_revision,
    )


async def stale_pending_runs(db: AsyncSession, *, session_id: uuid.UUID, reason: str) -> int:
    """Mark queued/running runs of a session STALE (they must not write)."""

    now = datetime.now(UTC)
    runs = (
        await db.scalars(
            select(AgentRun).where(
                AgentRun.session_id == session_id,
                AgentRun.status.in_((RunStatus.QUEUED.value, RunStatus.RUNNING.value)),
            )
        )
    ).all()
    for run in runs:
        run.status = RunStatus.STALE.value
        run.stale_reason = reason
        run.completed_at = now
        run.lease_token = None
    if runs:
        await db.flush()
    return len(runs)


async def apply_lesson_event(
    db: AsyncSession,
    *,
    session: LessonSession,
    event: LessonEvent,
    reference: str | None = None,
    profile: LearnerProfile | None = None,
) -> dict[str, Any]:
    """Apply one local legal event; phase and lifecycle stay independent."""

    current_phase, current_lifecycle, revision = await load_phase_state(session)
    try:
        transition = resolve_event(event, phase=current_phase, lifecycle=current_lifecycle)
    except IllegitimateTransition as exc:
        raise LessonEventRejected(str(exc)) from exc

    if transition.requires_real_activity:
        real, _ = await evidence_counts(db, session.id)
        if not completion_allowed(real_activities=real):
            raise CompletionNotAllowed(
                "completion requires a real learning activity and an explicit request"
            )

    if transition.evidence is not None:
        kind, outcome = transition.evidence
        await record_evidence(db, session=session, kind=kind, outcome=outcome, reference=reference)

    new_phase = transition.to_phase or current_phase
    new_lifecycle = transition.lifecycle or current_lifecycle
    session.phase = new_phase.value
    session.lifecycle = new_lifecycle.value
    session.phase_revision = revision + 1
    db.add(
        TeachingPhaseEvent(
            session_id=session.id,
            owner_user_id=session.owner_user_id,
            event=event.value,
            from_phase=current_phase.value,
            to_phase=new_phase.value,
            lifecycle=new_lifecycle.value,
            phase_revision=session.phase_revision,
        )
    )

    snapshot, created = await ensure_policy_snapshot(db, session=session, profile=profile)
    staled = 0
    if created:
        # Evidence or profile moved: pending runs bound to the old snapshot lose.
        staled = await stale_pending_runs(db, session_id=session.id, reason="POLICY_CHANGED")
    await db.commit()
    await db.refresh(session)

    summary = await evidence_summary(db, session.id)
    return {
        "phase": session.phase,
        "lifecycle": session.lifecycle,
        "phase_revision": session.phase_revision,
        "policy_snapshot_id": str(snapshot.id),
        "policy_created": created,
        "staled_runs": staled,
        "evidence": summary,
        "triggers_tutor": transition.triggers_tutor,
    }


async def start_event_run(
    db: AsyncSession,
    *,
    user: User,
    session: LessonSession,
    event: LessonEvent,
    operation: str,
    message: str,
    policy_snapshot_id: uuid.UUID | None,
    idempotency_key: str | None = None,
) -> tuple[AgentRun, bool]:
    """Create the run for a tutor-triggering event, idempotently."""

    key = idempotency_key or f"{event.value.lower()}:{session.id}:{session.phase_revision}"
    digest = request_hash(operation=operation, message=f"{event.value}:{message}")

    def _insert_statement(insert_key: str):
        return (
            pg_insert(AgentRun)
            .values(
                id=uuid.uuid4(),
                session_id=session.id,
                owner_user_id=user.id,
                operation=operation,
                event=event.value,
                idempotency_key=insert_key,
                request_hash=digest,
                policy_snapshot_id=policy_snapshot_id,
                status=RunStatus.QUEUED.value,
                attempt=1,
            )
            .on_conflict_do_nothing(index_elements=["owner_user_id", "idempotency_key"])
            .returning(AgentRun.id)
        )

    inserted_id = await db.scalar(_insert_statement(key))
    if inserted_id is not None:
        await db.commit()
        run = await db.scalar(select(AgentRun).where(AgentRun.id == inserted_id))
        if run is None:  # pragma: no cover
            raise RuntimeError("run vanished after insert")
        return run, True

    # No rollback here: rollback would expire the locked LessonSession row (and
    # drop the row lock), which the caller still needs for the phase payload.
    existing_id = await db.scalar(
        select(AgentRun.id).where(
            AgentRun.owner_user_id == user.id, AgentRun.idempotency_key == key
        )
    )
    if existing_id is None:  # pragma: no cover
        raise RunConflict("idempotency key is claimed by a vanished run")
    existing = await db.scalar(select(AgentRun).where(AgentRun.id == existing_id))
    if existing is None:  # pragma: no cover
        raise RunConflict("idempotency key is claimed by a vanished run")
    if existing.request_hash != digest:
        raise RunConflict("idempotency key reused with a different request")
    if existing.status == RunStatus.STALE.value:
        # A STALE run produced nothing: retire its key so the event can be
        # served freshly, while concurrent retries still converge on a single
        # replacement (the second insert conflicts on the original key).
        retired = f"{key}#stale-{uuid.uuid4().hex[:8]}"
        existing.idempotency_key = retired
        await db.flush()
        inserted_id = await db.scalar(_insert_statement(key))
        if inserted_id is not None:
            await db.commit()
            run = await db.scalar(select(AgentRun).where(AgentRun.id == inserted_id))
            if run is None:  # pragma: no cover
                raise RuntimeError("run vanished after insert")
            return run, True
        winner_id = await db.scalar(
            select(AgentRun.id).where(
                AgentRun.owner_user_id == user.id, AgentRun.idempotency_key == key
            )
        )
        if winner_id is None:  # pragma: no cover
            raise RunConflict("idempotency key is claimed by a vanished run")
        winner = await db.scalar(select(AgentRun).where(AgentRun.id == winner_id))
        if winner is None:  # pragma: no cover
            raise RunConflict("idempotency key is claimed by a vanished run")
        if winner.request_hash != digest:
            raise RunConflict("idempotency key reused with a different request")
        return winner, False
    return existing, False


async def mark_session_stale(db: AsyncSession, *, session: LessonSession, reason: str) -> int:
    """Chapter switch / policy change: the old session stops accepting writes."""

    session.lifecycle = Lifecycle.STALE.value
    staled = await stale_pending_runs(db, session_id=session.id, reason=reason)
    await db.commit()
    return staled
