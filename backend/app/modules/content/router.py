"""Student-facing content API: catalogue, versioned reading and page context.

Every endpoint resolves the viewer from the server-side session (T05) and
applies the same visibility rules as the service layer, so a client can never
read an unpublished, withdrawn, wrong-stage or fixture revision by guessing an
id. Only the single textbook-answer endpoint returns fixed reference answers;
ordinary content responses never contain answers or hidden tests.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.database import get_session
from app.modules.content.schemas import (
    ChapterDetailDTO,
    CourseListDTO,
    CourseSummaryDTO,
    PageContextDTO,
    PageContextRequest,
    ReadingEventReceipt,
    ReadingEventRequest,
    ReadingStateDTO,
    SelfTestAnswerDTO,
    ViewerScope,
)
from app.modules.content.service import (
    ContentNotVisible,
    InvalidContext,
    latest_reading_state,
    record_reading_event,
    resolve_page_context,
    viewer_scope_from_profile,
    visible_chapter_detail,
    visible_course,
    visible_courses,
    visible_self_test_answer,
)
from app.modules.identity.dependencies import (
    SessionContext,
    csrf_dependency,
    require_student,
)
from app.modules.identity.models import LearnerProfile

router = APIRouter(tags=["content"])

CHAPTER_UNAVAILABLE = "章节不可用"


async def _viewer(request: Request, context: SessionContext, db: AsyncSession) -> ViewerScope:
    settings: Settings = request.app.state.settings
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    return viewer_scope_from_profile(profile, settings)


@router.get("/courses", response_model=CourseListDTO)
async def list_courses(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> CourseListDTO:
    viewer = await _viewer(request, context, db)
    return CourseListDTO(items=await visible_courses(db, viewer))


@router.get("/courses/{course_id}", response_model=CourseSummaryDTO)
async def get_course(
    course_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> CourseSummaryDTO:
    viewer = await _viewer(request, context, db)
    course = await visible_course(db, course_id=course_id, viewer=viewer)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程不可用")
    return course


@router.get("/chapters/{chapter_id}", response_model=ChapterDetailDTO)
async def get_chapter(
    chapter_id: uuid.UUID,
    request: Request,
    revision: int | None = Query(default=None, ge=1, le=10_000),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> ChapterDetailDTO:
    viewer = await _viewer(request, context, db)
    chapter = await visible_chapter_detail(
        db, chapter_id=chapter_id, viewer=viewer, revision=revision
    )
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CHAPTER_UNAVAILABLE)
    return chapter


@router.get(
    "/chapters/{chapter_id}/self-test-answers/{question_id}", response_model=SelfTestAnswerDTO
)
async def get_self_test_answer(
    chapter_id: uuid.UUID,
    question_id: str,
    request: Request,
    revision_id: uuid.UUID = Query(...),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> SelfTestAnswerDTO:
    viewer = await _viewer(request, context, db)
    answer = await visible_self_test_answer(
        db,
        chapter_id=chapter_id,
        revision_id=revision_id,
        question_id=question_id,
        viewer=viewer,
    )
    if answer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="参考答案暂不可用")
    return answer


@router.get("/chapters/{chapter_id}/reading-state", response_model=ReadingStateDTO | None)
async def get_reading_state(
    chapter_id: uuid.UUID,
    request: Request,
    revision: int | None = Query(default=None, ge=1, le=10_000),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> ReadingStateDTO | None:
    viewer = await _viewer(request, context, db)
    try:
        return await latest_reading_state(
            db,
            viewer=viewer,
            user_id=context.user.id,
            chapter_id=chapter_id,
            revision=revision,
        )
    except ContentNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=CHAPTER_UNAVAILABLE
        ) from None


@router.post(
    "/content/page-context",
    response_model=PageContextDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def post_page_context(
    payload: PageContextRequest,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> PageContextDTO:
    viewer = await _viewer(request, context, db)
    try:
        return await resolve_page_context(db, viewer=viewer, payload=payload)
    except ContentNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=CHAPTER_UNAVAILABLE
        ) from None
    except InvalidContext as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from None


@router.post(
    "/reading-events",
    response_model=ReadingEventReceipt,
    dependencies=[Depends(csrf_dependency)],
)
async def post_reading_event(
    payload: ReadingEventRequest,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> ReadingEventReceipt:
    viewer = await _viewer(request, context, db)
    try:
        return await record_reading_event(
            db, viewer=viewer, user_id=context.user.id, payload=payload
        )
    except ContentNotVisible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=CHAPTER_UNAVAILABLE
        ) from None
    except InvalidContext as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from None
