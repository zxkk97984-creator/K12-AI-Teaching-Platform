"""Next-step API: read-only GET, explicit refresh, CSRF-protected feedback (T19)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.recommendation.service import (
    FeedbackRevisionConflict,
    apply_feedback,
    compute_next_step,
    list_feedback,
    refresh_snapshot,
    snapshot_detail,
)

router = APIRouter(tags=["recommendation"])


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_key: str = Field(min_length=3, max_length=200)
    action: Literal["IGNORE", "RESTORE"]
    base_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=200)


def _settings(request: Request):
    return request.app.state.settings


async def _read_model(db: AsyncSession, *, owner_user_id: uuid.UUID, settings) -> dict[str, Any]:
    body = await compute_next_step(db, owner_user_id=owner_user_id, settings=settings)
    body["feedback"] = await list_feedback(db, owner_user_id=owner_user_id)
    return body


@router.get("/recommendation/next-step")
async def read_next_step(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Pure read: computes the decision without writing anything."""

    return await _read_model(db, owner_user_id=context.user.id, settings=_settings(request))


@router.get("/recommendation/snapshots/{snapshot_id}")
async def read_snapshot(
    snapshot_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    body = await snapshot_detail(db, owner_user_id=context.user.id, snapshot_id=snapshot_id)
    if body is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="建议快照不存在")
    return body


@router.post("/recommendation/refresh", dependencies=[Depends(csrf_dependency)])
async def refresh_recommendation(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = _settings(request)
    stats = await refresh_snapshot(db, owner_user_id=context.user.id, settings=settings)
    body = await _read_model(db, owner_user_id=context.user.id, settings=settings)
    body["projection"] = {
        "created": stats["created"],
        "inputs_hash": stats["inputs_hash"],
        "source_revision": (stats["snapshot"] or {}).get("source_revision"),
    }
    return body


@router.post("/recommendation/feedback", dependencies=[Depends(csrf_dependency)])
async def write_feedback(
    body: FeedbackRequest,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await apply_feedback(
            db,
            owner_user_id=context.user.id,
            subject_key=body.subject_key,
            action=body.action,
            base_revision=body.base_revision,
            reason=body.reason,
        )
    except FeedbackRevisionConflict as caught:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"RECOMMENDATION_FEEDBACK_CONFLICT: {caught}",
        ) from caught
