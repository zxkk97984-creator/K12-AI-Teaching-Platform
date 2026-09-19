"""Admin Designer API (T15).

Only the teaching/curriculum staff surface exists here: the student quiz UI and
the student answer flow belong to T16. Every response is built from
``dto`` projections that cannot carry the server-side answer object.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.assessment.dto import draft_public, job_public
from app.modules.assessment.errors import DesignerRequestInvalid
from app.modules.assessment.service import create_quiz_draft_job, get_draft, list_jobs
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_admin

router = APIRouter(tags=["assessment"])


class GenerationJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: uuid.UUID = Field(description="要出题的章节；其余参数一律由服务端推导")


@router.post(
    "/admin/generation-jobs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_generation_job(
    body: GenerationJobCreate,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        outcome = await create_quiz_draft_job(
            db,
            settings=request.app.state.settings,
            gateway=request.app.state.gateway,
            requester=context.user,
            chapter_id=body.chapter_id,
        )
    except DesignerRequestInvalid as exc:
        http_status = (
            status.HTTP_404_NOT_FOUND
            if exc.code == "CHAPTER_NOT_FOUND"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=http_status, detail=f"{exc.code}: {exc.detail}") from exc
    return {
        "job": job_public(outcome.job),
        "draft": draft_public(outcome.draft) if outcome.draft is not None else None,
    }


@router.get("/admin/generation-jobs")
async def list_generation_jobs(
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    jobs = await list_jobs(db, requester=context.user)
    return {"items": [job_public(job) for job in jobs]}


@router.get("/admin/quiz-drafts/{draft_id}")
async def get_quiz_draft(
    draft_id: uuid.UUID,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    draft = await get_draft(db, requester=context.user, draft_id=draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="题稿不存在")
    return {"draft": draft_public(draft)}
