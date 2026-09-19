"""Student growth API (T18 K1/K4/K7/K9).

Reads never create a projection or an observation: ``GET /growth/overview`` only
serves already-projected, owner-scoped facts. Re-projection is an explicit,
idempotent, CSRF-protected student action (or a worker step before a tutor turn).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.learning.projection import (
    evidence_detail,
    growth_overview,
    needs_projection,
    project_and_observe,
)
from app.modules.memory.service import derive_candidates, list_memories

router = APIRouter(tags=["growth"])


async def _overview(db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int) -> dict[str, Any]:
    body = await growth_overview(db, owner_user_id=owner_user_id)
    body["memories"] = await list_memories(db, owner_user_id=owner_user_id)
    body["needs_projection"] = await needs_projection(db, owner_user_id=owner_user_id, limit=limit)
    body["projection_rule_version"] = "k12.evidence.projection.v1"
    return body


@router.get("/growth/overview")
async def read_growth_overview(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = request.app.state.settings
    return await _overview(
        db, owner_user_id=context.user.id, limit=settings.growth_projection_max_events
    )


@router.post(
    "/growth/projection",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(csrf_dependency)],
)
async def reproject_growth(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = request.app.state.settings
    stats = await project_and_observe(
        db, owner_user_id=context.user.id, limit=settings.growth_projection_max_events
    )
    derived = await derive_candidates(
        db, owner_user_id=context.user.id, limit=settings.growth_projection_max_events
    )
    body = await _overview(
        db, owner_user_id=context.user.id, limit=settings.growth_projection_max_events
    )
    body["projection"] = {**stats, "memories": derived}
    return body


@router.get("/growth/evidence/{evidence_id}")
async def read_evidence_detail(
    evidence_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    body = await evidence_detail(db, owner_user_id=context.user.id, evidence_id=evidence_id)
    if body is None:
        # Another student's evidence id is simply absent for this caller.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="依据记录不存在")
    return body
