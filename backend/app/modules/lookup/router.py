from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.identity.dependencies import SessionContext, require_student
from app.modules.identity.models import LearnerProfile
from app.modules.lookup.schemas import LookupTarget, LookupTargetDTO
from app.modules.lookup.service import LookupRuntime
from app.modules.lookup.targets import resolve_target

router = APIRouter(tags=["lookup"])


@router.get("/learning/lookup-target", response_model=LookupTargetDTO)
async def lookup_target(
    request: Request,
    target: LookupTarget = Depends(),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
):
    profile = await db.scalar(
        select(LearnerProfile).where(
            LearnerProfile.user_id == context.user.id,
        )
    )
    runtime = LookupRuntime(
        db, context.user.id, profile.stage if profile else "", request.app.state.settings
    )
    try:
        route = await resolve_target(runtime, target)
    except ValueError:
        route = None
    if not route:
        raise HTTPException(404, "此记录或版本已不可用，请重新询问老师获取当前结果。")
    return LookupTargetDTO(route=route)
