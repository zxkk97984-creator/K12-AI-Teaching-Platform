"""Memory candidate API: student-owned confirm/dispute/edit/forget (T18 K2/K5/K9).

Mounted under /api/v1/growth/**: the frozen identity exporter treats any path
starting with "/api/v1/me" as an identity path, so a "/api/v1/memories" route
would leak into contracts/openapi.identity.json. Keeping memory under the growth
namespace keeps that frozen document byte-identical (and matches the product
spec's /growth/memories entry).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.memory.service import (
    MemoryForgotten,
    MemoryNotFound,
    MemoryRevisionConflict,
    MemoryTransitionInvalid,
    apply_memory_event,
    list_memories,
    memory_detail,
)

router = APIRouter(tags=["memory"])

_CODE_STATUS = {
    "MEMORY_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "MEMORY_REVISION_CONFLICT": status.HTTP_409_CONFLICT,
    "MEMORY_TRANSITION_INVALID": status.HTTP_409_CONFLICT,
    "MEMORY_FORGOTTEN": status.HTTP_409_CONFLICT,
}


class MemoryActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["CONFIRM", "DISPUTE", "EDIT", "FORGET"]
    base_revision: int = Field(ge=1)
    statement: str | None = Field(default=None, max_length=400)
    reason: str | None = Field(default=None, max_length=200)


@router.get("/growth/memories")
async def read_memories(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    items = await list_memories(db, owner_user_id=context.user.id)
    return {
        "items": items,
        "notice": "记忆由你掌控：只有你确认（ACTIVE）的建议才会进入教学上下文；"
        "候选、质疑与已遗忘都不会被注入。",
    }


@router.get("/growth/memories/{memory_id}")
async def read_memory(
    memory_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    body = await memory_detail(db, owner_user_id=context.user.id, memory_id=memory_id)
    if body is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记忆不存在")
    return body


@router.post(
    "/growth/memories/{memory_id}/events",
    dependencies=[Depends(csrf_dependency)],
)
async def write_memory_event(
    memory_id: uuid.UUID,
    body: MemoryActionRequest,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await apply_memory_event(
            db,
            owner_user_id=context.user.id,
            memory_id=memory_id,
            action=body.action,
            base_revision=body.base_revision,
            statement=body.statement,
            reason=body.reason,
        )
    except MemoryNotFound as caught:
        _raise("MEMORY_NOT_FOUND", str(caught))
    except MemoryRevisionConflict as caught:
        _raise("MEMORY_REVISION_CONFLICT", str(caught))
    except MemoryForgotten as caught:
        _raise("MEMORY_FORGOTTEN", str(caught))
    except MemoryTransitionInvalid as caught:
        _raise("MEMORY_TRANSITION_INVALID", str(caught))


def _raise(code: str, detail: str) -> None:
    raise HTTPException(
        status_code=_CODE_STATUS.get(code, status.HTTP_409_CONFLICT), detail=f"{code}: {detail}"
    )
