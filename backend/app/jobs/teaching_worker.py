"""Lease-based run worker (QA10).

The worker never holds a database transaction across the gateway call:

* phase 1 (short transaction): claim the QUEUED run with a lease token;
* phase 2 (no transaction, no session): call the gateway with a cancel signal;
* phase 3 (short transaction): lease-guarded finalise — stale or cancelled
  results are recorded honestly and never overwrite newer state.

Mutual exclusion is the database lease, not a process-local boolean, so two
worker processes cannot both execute the same run. Recovery after a restart marks
interrupted runs STALE instead of silently re-charging the upstream.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.integrations.knodo import AgentGateway, GatewayStatus
from app.integrations.knodo.fixture import FixtureScenario
from app.integrations.knodo.operations import Operation
from app.modules.learning.projection import merge_learner_context, project_and_observe
from app.modules.learning.service import snapshot_for
from app.modules.memory.service import build_learner_context, derive_candidates
from app.modules.recommendation.service import refresh_snapshot as refresh_recommendation
from app.modules.teaching.context import build_teaching_request
from app.modules.teaching.models import AgentRun, LessonSession
from app.modules.teaching.service import (
    acquire_lease,
    finalize_run,
    record_binding,
)
from app.modules.teaching.validation import build_card, validate_assistant_output

logger = logging.getLogger(__name__)

# Process-local cancel signals only speed up cancellation *inside this process*.
# The authoritative cancel flag lives in the database.
_CANCEL_SIGNALS: dict[str, asyncio.Event] = {}


def session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = get_engine(settings.active_database_url, settings.app_env)
    return async_sessionmaker(engine, expire_on_commit=False)


def register_cancel_signal(run_id: str) -> asyncio.Event:
    event = asyncio.Event()
    _CANCEL_SIGNALS[run_id] = event
    return event


def signal_cancel(run_id: str) -> None:
    event = _CANCEL_SIGNALS.get(run_id)
    if event is not None:
        event.set()


async def execute_run(
    settings: Settings,
    gateway: AgentGateway,
    run_id: str,
    *,
    cancel_signal: asyncio.Event | None = None,
) -> str:
    """Run one queued turn. Returns the resulting run status string."""

    factory = session_factory(settings)
    async with factory() as db:
        token = await acquire_lease(db, run_id=run_id, ttl_seconds=settings.teaching_lease_seconds)
    if token is None:
        return "LEASE_HELD"

    async with factory() as db:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
        session = await db.scalar(select(LessonSession).where(LessonSession.id == run.session_id))
        # T18 K3: project this student's trusted events into evidence and derive
        # candidates *before* the request is built, so the turn can only see
        # valid evidence and ACTIVE (student-confirmed) memories. Read APIs never
        # do this; it is an event-triggered step of the run itself.
        #
        # It reuses this session (no extra pool checkout) and fails closed: a
        # projection problem must never break or delay teaching delivery, so the
        # turn simply runs without learner context and the state is retried on
        # the next run / explicit reprojection.
        learner_context: list[dict[str, Any]] = []
        try:
            await project_and_observe(
                db, owner_user_id=session.owner_user_id, limit=settings.growth_projection_max_events
            )
            await derive_candidates(
                db, owner_user_id=session.owner_user_id, limit=settings.growth_projection_max_events
            )
            learner_context = await build_learner_context(
                db,
                owner_user_id=session.owner_user_id,
                evidence_limit=settings.growth_context_evidence_limit,
                memory_limit=settings.growth_context_memory_limit,
            )
            # T19: a tutor run is an event, so the single next-step decision is
            # re-projected here (same session, same fail-closed rule). The read
            # API never triggers this.
            await refresh_recommendation(db, owner_user_id=session.owner_user_id, settings=settings)
        except Exception:  # pragma: no cover - defensive, logged below
            await db.rollback()
            logger.warning(
                "learner context projection failed; continuing without it", exc_info=True
            )
        context = dict(session.context)
        allowance = session.fixture_allowance
        student_input = await _student_input(db, run)
        operation = Operation(run.operation)
        stage = session.stage
        grade = session.grade
        base_revision = session.base_revision
        event = run.event or "ASK"
        current_phase = session.phase
        policy_snapshot = (
            await snapshot_for(db, run.policy_snapshot_id)
            if run.policy_snapshot_id is not None
            else None
        )
        policy = policy_snapshot.policy if policy_snapshot is not None else None

    request = build_teaching_request(
        session_id=str(session.id),
        context=context,
        operation=operation.value,
        student_input=student_input,
        base_revision=base_revision,
        stage=stage,
        grade=grade,
        preferred_style="AUTO",
        fixture_allowance=allowance,
        event=event,
        current_phase=current_phase,
        policy=policy,
    )
    # T18 K3: attach the learner's valid evidence and ACTIVE memories through
    # the existing (frozen) `evidence` field, and widen only this run's allowed
    # evidence ids so validation keeps rejecting anything not injected here.
    request["evidence"] = merge_learner_context(context, learner_context)

    signal = cancel_signal or _CANCEL_SIGNALS.get(run_id)
    # Dev/test only: an explicitly configured fixture delay turns the synthetic
    # backend into the DELAY scenario so cancellation/reconnect can be observed.
    fixture_scenario = (
        FixtureScenario.DELAY
        if settings.gateway_mode == "fixture" and settings.teaching_fixture_delay_seconds > 0
        else FixtureScenario.SUCCESS
    )
    result = await gateway.invoke(
        operation.value,
        request,
        scenario=fixture_scenario,
        timeout_seconds=settings.gateway_timeout_seconds,
        cancel=signal,
        delay_seconds=settings.teaching_fixture_delay_seconds or None,
    )
    fixture = result.mode == "fixture"

    async with factory() as db:
        if result.status is GatewayStatus.CANCELLED:
            await record_binding(
                db,
                run=run,
                remote_kind="FIXTURE" if fixture else "KNODO",
                remote_id=result.invocation_id,
            )
            status = await finalize_run(
                db, run_id=run_id, lease_token=token, error_category=None, assistant=None
            )
            return status
        if result.status in (GatewayStatus.FAILED,):
            category = result.error.category.value if result.error else "UNKNOWN"
            await record_binding(
                db,
                run=run,
                remote_kind="FIXTURE" if fixture else "KNODO",
                remote_id=result.invocation_id,
            )
            return await finalize_run(db, run_id=run_id, lease_token=token, error_category=category)
        if result.status is GatewayStatus.INSUFFICIENT_EVIDENCE or result.output is None:
            await record_binding(
                db,
                run=run,
                remote_kind="FIXTURE" if fixture else "KNODO",
                remote_id=result.invocation_id,
            )
            return await finalize_run(
                db, run_id=run_id, lease_token=token, error_category="INSUFFICIENT_EVIDENCE"
            )

        problems = validate_assistant_output(
            operation=operation,
            payload=result.output,
            context=context,
            fixture_allowance=allowance,
        )
        await record_binding(
            db,
            run=run,
            remote_kind="FIXTURE" if fixture else "KNODO",
            remote_id=result.invocation_id,
        )
        if problems:
            return await finalize_run(
                db, run_id=run_id, lease_token=token, error_category=problems[0]
            )
        card = build_card(result.output, fixture=fixture)
        try:
            return await finalize_run(
                db,
                run_id=run_id,
                lease_token=token,
                assistant=card,
                gateway_invocation_id=result.invocation_id,
            )
        except Exception:
            # Persist an honest failure instead of leaving a silent half-state.
            logger.exception("teaching: saving the assistant card failed for run %s", run_id)
            await db.rollback()

    async with factory() as failure_db:
        return await finalize_run(
            failure_db, run_id=run_id, lease_token=token, error_category="SAVE_FAILED"
        )


async def _student_input(db: AsyncSession, run: AgentRun) -> str:
    from app.modules.teaching.models import ConversationMessage, MessageRole

    value = await db.scalar(
        select(ConversationMessage.content_markdown).where(
            ConversationMessage.run_id == run.id,
            ConversationMessage.role == MessageRole.USER.value,
        )
    )
    return value or ""


async def schedule_run(settings: Settings, gateway: AgentGateway, run_id: str) -> asyncio.Task[Any]:
    """Fire-and-forget worker task (the HTTP request returns 202 immediately)."""

    signal = register_cancel_signal(run_id)
    task = asyncio.create_task(execute_run(settings, gateway, run_id, cancel_signal=signal))
    task.add_done_callback(lambda finished: _CANCEL_SIGNALS.pop(run_id, None))
    return task


async def recover_runs(settings: Settings) -> int:
    from app.modules.teaching.service import recover_expired_runs

    factory = session_factory(settings)
    async with factory() as db:
        count = await recover_expired_runs(db)
    if count:
        logger.warning("teaching: recovered %s interrupted run(s) as STALE/CANCELLED", count)
    return count
