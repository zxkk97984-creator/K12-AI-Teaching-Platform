"""Conversation/run HTTP API: 202 accept + SSE progress + owner-scoped cancel."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.jobs.teaching_worker import schedule_run, session_factory, signal_cancel
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.identity.models import LearnerProfile
from app.modules.learning.policy import LearningPolicyError
from app.modules.learning.service import ensure_policy_snapshot, evidence_summary, snapshot_for
from app.modules.teaching.models import (
    TERMINAL_RUN_STATUSES,
    AgentRun,
    LessonSession,
    RunStatus,
)
from app.modules.teaching.phase import LessonEvent
from app.modules.teaching.schemas import (
    LessonEventRequest,
    LessonPhaseDTO,
    RunDTO,
    SessionCreateRequest,
    SessionDetail,
    SessionSummary,
    TurnAccepted,
    TurnCreateRequest,
)
from app.modules.teaching.service import (
    CompletionNotAllowed,
    LessonEventRejected,
    RunConflict,
    SessionBindingStale,
    SessionNotVisible,
    apply_lesson_event,
    create_session,
    create_turn,
    ensure_session_binding,
    get_run,
    get_session_detail,
    list_sessions,
    request_cancel,
    run_dto,
    stale_pending_runs,
    start_event_run,
)

router = APIRouter(tags=["teaching"])

_TERMINAL_EVENT = {
    RunStatus.SUCCEEDED.value: "done",
    RunStatus.FAILED.value: "failed",
    RunStatus.CANCELLED.value: "cancelled",
    RunStatus.STALE.value: "stale",
}


@router.post(
    "/lesson-sessions",
    response_model=SessionSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def open_session(
    body: SessionCreateRequest,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> SessionSummary:
    try:
        await create_session(
            db, settings=request.app.state.settings, user=context.user, chapter_id=body.chapter_id
        )
    except SessionNotVisible as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不可用") from exc
    rows = await list_sessions(db, user=context.user, limit=1)
    return rows[0]


@router.get("/lesson-sessions", response_model=list[SessionSummary])
async def list_lesson_sessions(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> list[SessionSummary]:
    return await list_sessions(db, user=context.user)


@router.get("/lesson-sessions/{session_id}", response_model=SessionDetail)
async def get_lesson_session(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> SessionDetail:
    detail = await get_session_detail(db, user=context.user, session_id=session_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return detail


@router.post(
    "/lesson-sessions/{session_id}/turns",
    response_model=TurnAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_lesson_turn(
    session_id: uuid.UUID,
    body: TurnCreateRequest,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> TurnAccepted:
    session = await db.scalar(
        select(LessonSession).where(
            LessonSession.id == session_id, LessonSession.owner_user_id == context.user.id
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    try:
        await ensure_session_binding(
            db, settings=request.app.state.settings, session=session, profile=profile
        )
    except SessionBindingStale as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该课时已随章节版本变化失效，请重新进入章节",
        ) from exc

    try:
        run, created = await create_turn(
            db,
            user=context.user,
            session=session,
            operation=body.operation,
            message=body.message,
            idempotency_key=body.idempotency_key,
        )
    except RunConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="同一幂等键对应不同请求体"
        ) from exc

    if created and request.app.state.settings.teaching_autorun:
        # The short transaction has committed: schedule the gateway call now.
        await schedule_run(request.app.state.settings, request.app.state.gateway, str(run.id))
    return TurnAccepted(run=await run_dto(db, run, replay=not created))


@router.get("/agent-runs/{run_id}", response_model=RunDTO)
async def get_agent_run(
    run_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> RunDTO:
    run = await get_run(db, user=context.user, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="运行不存在")
    return await run_dto(db, run)


@router.post(
    "/agent-runs/{run_id}/cancel",
    response_model=RunDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def cancel_agent_run(
    run_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> RunDTO:
    run = await request_cancel(db, user=context.user, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="运行不存在")
    signal_cancel(str(run_id))  # fast path for the in-process worker only
    return await run_dto(db, run)


@router.get("/agent-runs/{run_id}/events")
async def stream_agent_run(
    run_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    run = await get_run(db, user=context.user, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="运行不存在")

    settings = request.app.state.settings
    owner_id = context.user.id

    async def event_stream() -> AsyncIterator[bytes]:
        factory = session_factory(settings)
        last_status: str | None = None
        last_emit = time.monotonic()
        while True:
            async with factory() as stream_db:
                current = await stream_db.scalar(
                    select(AgentRun).where(
                        AgentRun.id == run_id, AgentRun.owner_user_id == owner_id
                    )
                )
                if current is None:
                    yield b'event: failed\ndata: {"status": "MISSING"}\n\n'
                    return
                payload = (await run_dto(stream_db, current)).model_dump(mode="json")
            if payload["status"] != last_status:
                last_status = payload["status"]
                last_emit = time.monotonic()
                body_text = json.dumps(payload, ensure_ascii=False)
                yield f"event: update\ndata: {body_text}\n\n".encode()
            if payload["status"] in TERMINAL_RUN_STATUSES:
                event = _TERMINAL_EVENT.get(payload["status"], "failed")
                terminal_text = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event}\ndata: {terminal_text}\n\n".encode()
                return
            if time.monotonic() - last_emit >= settings.teaching_sse_heartbeat_seconds:
                last_emit = time.monotonic()
                yield b": ping\n\n"
            await asyncio.sleep(settings.teaching_sse_poll_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


async def _owned_session(
    db: AsyncSession, *, user_id, session_id: uuid.UUID, for_update: bool = False
) -> LessonSession:
    statement = select(LessonSession).where(
        LessonSession.id == session_id, LessonSession.owner_user_id == user_id
    )
    if for_update:
        # Serialise concurrent events for one lesson (double tab / refresh race)
        # so policy snapshot creation and opening runs stay single-shot.
        statement = statement.with_for_update().execution_options(populate_existing=True)
    session = await db.scalar(statement)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return session


async def _phase_payload(
    db: AsyncSession,
    *,
    session: LessonSession,
    run: AgentRun | None = None,
    proactive: str | None = None,
) -> LessonPhaseDTO:
    snapshot = (
        await snapshot_for(db, session.policy_snapshot_id) if session.policy_snapshot_id else None
    )

    return LessonPhaseDTO(
        session_id=session.id,
        phase=session.phase,
        lifecycle=session.lifecycle,
        phase_revision=session.phase_revision,
        policy=snapshot.policy if snapshot else {},
        policy_snapshot_id=session.policy_snapshot_id,
        evidence=await evidence_summary(db, session.id),
        run=await run_dto(db, run) if run is not None else None,
        proactive_opening=proactive,
    )


@router.get("/lesson-sessions/{session_id}/phase", response_model=LessonPhaseDTO)
async def get_lesson_phase(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> LessonPhaseDTO:
    session = await _owned_session(db, user_id=context.user.id, session_id=session_id)
    return await _phase_payload(db, session=session)


@router.post(
    "/lesson-sessions/{session_id}/events",
    response_model=LessonPhaseDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def post_lesson_event(
    session_id: uuid.UUID,
    body: LessonEventRequest,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> LessonPhaseDTO:
    session = await _owned_session(
        db, user_id=context.user.id, session_id=session_id, for_update=True
    )
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    try:
        await ensure_session_binding(
            db, settings=request.app.state.settings, session=session, profile=profile
        )
    except SessionBindingStale as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该课时已随章节版本或学段变化失效，请重新进入章节",
        ) from exc
    try:
        event = LessonEvent(body.event)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="未知的课程事件"
        ) from exc

    try:
        if event in (LessonEvent.ENTER, LessonEvent.ASK):
            snapshot, policy_created = await ensure_policy_snapshot(
                db, session=session, profile=profile
            )
            if policy_created:
                # Stage/grade/preference/evidence moved: anything still in flight
                # for the old opening loses before a new run is bound.
                await stale_pending_runs(db, session_id=session.id, reason="POLICY_CHANGED")
            await db.commit()
            await db.refresh(session)
            if event is LessonEvent.ENTER:
                proactive_allowed = bool(
                    snapshot.policy.get("proactive_opening_allowed", True)
                ) and bool(profile.proactive_guidance_enabled if profile else True)
                if not proactive_allowed:
                    return await _phase_payload(
                        db, session=session, proactive="DISABLED_BY_PREFERENCE"
                    )
                message = body.message or "学生进入章节，请给出主动开场引导"
                default_key = f"enter:{session.id}:{session.phase_revision}:{snapshot.id}"
            else:
                if not body.message:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="插问需要内容",
                    )
                message = body.message
                # A student question is a fresh turn unless the caller pins a key.
                default_key = f"ask:{session.id}:{uuid.uuid4().hex}"
            run, created = await start_event_run(
                db,
                user=context.user,
                session=session,
                event=event,
                operation="TEACH_TURN",
                message=message,
                policy_snapshot_id=snapshot.id,
                idempotency_key=body.idempotency_key or default_key,
            )
            if created and request.app.state.settings.teaching_autorun:
                await schedule_run(
                    request.app.state.settings, request.app.state.gateway, str(run.id)
                )
            proactive = (
                ("TRIGGERED" if created else "ALREADY_OPENED")
                if event is LessonEvent.ENTER
                else None
            )
            return await _phase_payload(db, session=session, run=run, proactive=proactive)

        state = await apply_lesson_event(
            db, session=session, event=event, reference=body.reference, profile=profile
        )
    except CompletionNotAllowed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="完成需要真实活动与显式完成请求"
        ) from exc
    except LessonEventRejected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RunConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="同一幂等键对应不同请求体"
        ) from exc
    except LearningPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return await _phase_payload(
        db, session=session, proactive=("TRIGGERED" if state["triggers_tutor"] else None)
    )


@router.get("/lesson-sessions/{session_id}/policy")
async def get_lesson_policy(
    session_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    session = await _owned_session(db, user_id=context.user.id, session_id=session_id)
    snapshot = (
        await snapshot_for(db, session.policy_snapshot_id) if session.policy_snapshot_id else None
    )
    if snapshot is None:
        return {"policy": None, "phase": session.phase, "lifecycle": session.lifecycle}
    return {
        "policy": snapshot.policy,
        "policy_snapshot_id": str(snapshot.id),
        "evidence_level": snapshot.evidence_level,
        "input_revision": snapshot.input_revision,
        "phase": session.phase,
        "lifecycle": session.lifecycle,
    }
