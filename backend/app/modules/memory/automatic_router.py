import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.memory.automatic import (
    history_backfill,
    item_action,
    overview,
    settings_update,
    state_for,
    utcnow,
)
from app.modules.memory.automatic_models import MemoryTask, PersonalMemoryEvent, PersonalMemoryItem
from app.modules.memory.contracts import MemoryItemView, MemoryOverviewView

router = APIRouter(prefix="/growth/personal-memory", tags=["personal-memory"])


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    auto_enabled: bool
    use_enabled: bool


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1)
    action: Literal["EDIT", "FORGET", "RESTORE", "ALLOW_AUTO", "CONFIRM"]
    statement: str | None = Field(default=None, max_length=400)


class BackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class TaskAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["CANCEL", "RETRY"]


@router.get("", response_model=MemoryOverviewView)
async def read_overview(
    q: str = Query(default="", max_length=100),
    category: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    return await overview(db, context.user.id, q, category, offset, limit)


@router.patch(
    "/settings", response_model=MemoryOverviewView, dependencies=[Depends(csrf_dependency)]
)
async def write_settings(
    body: SettingsUpdate,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await settings_update(db, context.user.id, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return await overview(db, context.user.id)


@router.post(
    "/items/{item_id}/events",
    response_model=MemoryItemView,
    dependencies=[Depends(csrf_dependency)],
)
async def write_item(
    item_id: uuid.UUID,
    body: ItemUpdate,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    try:
        return await item_action(db, context.user.id, item_id, **body.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/items/{item_id}/events")
async def read_events(
    item_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    item = await db.scalar(
        select(PersonalMemoryItem).where(
            PersonalMemoryItem.id == item_id, PersonalMemoryItem.owner_user_id == context.user.id
        )
    )
    if item is None:
        raise HTTPException(404, "记忆不存在")
    rows = await db.scalars(
        select(PersonalMemoryEvent)
        .where(
            PersonalMemoryEvent.item_id == item_id,
            PersonalMemoryEvent.owner_user_id == context.user.id,
        )
        .order_by(PersonalMemoryEvent.revision.desc())
        .limit(100)
    )
    return {
        "items": [
            {
                "revision": r.revision,
                "action": r.action,
                "statement": r.statement,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    }


@router.post("/backfill", dependencies=[Depends(csrf_dependency)], status_code=202)
async def backfill(
    body: BackfillRequest,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    try:
        return await history_backfill(db, context.user.id, body.session_ids)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/tasks/{task_id}/events", dependencies=[Depends(csrf_dependency)])
async def update_task(
    task_id: uuid.UUID,
    body: TaskAction,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    state = await state_for(db, context.user.id, lock=True)
    task = await db.scalar(
        select(MemoryTask)
        .where(MemoryTask.id == task_id, MemoryTask.owner_user_id == context.user.id)
        .with_for_update()
    )
    if task is None:
        raise HTTPException(404, "任务不存在")
    if body.action == "CANCEL":
        if task.status in ("QUEUED", "RUNNING", "RETRY_REQUIRED"):
            task.status, task.reason = "CANCELLED", "USER_CANCELLED"
    else:
        if not state.auto_enabled or task.status != "RETRY_REQUIRED":
            raise HTTPException(409, "任务当前不可重试")
        task.status, task.reason, task.available_at = "QUEUED", None, utcnow()
    await db.commit()
    return {"id": str(task.id), "status": task.status}
