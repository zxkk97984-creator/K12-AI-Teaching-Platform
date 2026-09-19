"""Student animation API: filtered catalogue, one definition, validated spec.

The client receives data only: a template id, a bounded parameter schema, the
narration and a text alternative. Step generation happens in the front-end pure
functions; this API never returns executable content and never proxies a URL.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.database import get_session
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import viewer_scope_from_profile
from app.modules.identity.dependencies import (
    SessionContext,
    csrf_dependency,
    require_student,
)
from app.modules.identity.models import LearnerProfile
from app.modules.resources.animation_service import (
    AnimationError,
    animation_spec,
    load_visible_animation,
    public_definition,
    visible_animations,
)

router = APIRouter(tags=["animations"])


class AnimationSpecRequest(BaseModel):
    """Teacher/student supplied parameters; validated against the schema."""

    model_config = ConfigDict(extra="forbid")

    params: dict[str, Any] = Field(default_factory=dict)


async def _viewer(context: SessionContext, db: AsyncSession, settings: Settings) -> ViewerScope:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    return viewer_scope_from_profile(profile, settings)


def _raise(error: AnimationError) -> None:
    raise HTTPException(status_code=error.status_code, detail=f"{error.code}: {error.message}")


@router.get("/animations")
async def list_animations(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    viewer = await _viewer(context, db, settings)
    items = [public_definition(entry) for entry in await visible_animations(db, viewer=viewer)]
    profile = viewer.profile.value if hasattr(viewer.profile, "value") else str(viewer.profile)
    return {"items": items, "profile": profile}


@router.get("/animations/{animation_id}")
async def read_animation(
    animation_id: str,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    viewer = await _viewer(context, db, settings)
    try:
        entry = await load_visible_animation(db, viewer=viewer, identifier=animation_id)
    except AnimationError as error:
        _raise(error)
    return public_definition(entry)


@router.post(
    "/animations/{animation_id}/spec",
    dependencies=[Depends(csrf_dependency)],
)
async def read_animation_spec(
    animation_id: str,
    body: AnimationSpecRequest,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Validate parameters before the client is allowed to generate steps."""

    settings: Settings = request.app.state.settings
    viewer = await _viewer(context, db, settings)
    try:
        return await animation_spec(db, viewer=viewer, identifier=animation_id, params=body.params)
    except AnimationError as error:
        _raise(error)


__all__ = ["router"]
