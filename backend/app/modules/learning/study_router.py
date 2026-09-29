"""Student learning workbench API.

This router composes the existing content, resource and animation visibility
services into one owner-scoped catalogue. It adds only the small durable facts
needed by the workbench: bookmarks and explicit open history. Reading progress
continues to use ``content_reading_events`` and is never inferred from a mere
open event.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.database import get_session
from app.modules.content.models import ChapterRevision, KnowledgePoint, ReadingEvent
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import (
    viewer_scope_from_profile,
    visible_chapter_detail,
    visible_course,
    visible_courses,
)
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.identity.models import LearnerProfile
from app.modules.interactive.models import InteractiveRevision
from app.modules.learning.models import LearningBookmark, LearningOpenEvent, PicturebookProgress
from app.modules.learning.study_content import visible_guided_animation, visible_picturebooks
from app.modules.resources.animation_service import (
    AnimationError,
    load_visible_animation,
    public_definition,
    visible_animations,
)
from app.modules.resources.models import ResourceKnowledgePoint, ResourceVariant
from app.modules.resources.service import (
    ResourceError,
    list_student_resources,
    load_visible_resource,
    resource_detail,
    store_for,
)

router = APIRouter(tags=["learning"])

TargetKind = Literal["COURSE", "RESOURCE", "ANIMATION"]
HistoryKind = Literal["READING", "OPEN"]
TargetId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
PICTUREBOOK_IDS = frozenset(("crow", "tortoise"))


@router.get("/learning/student-content")
async def read_student_content(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The packaged synthetic stories and guided animation for this account stage."""
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="请先选择学段")
    return {
        "stage": profile.stage,
        "picturebooks": visible_picturebooks(profile.stage),
        "guided_animation": visible_guided_animation(profile.stage),
    }


class LearningItemDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TargetKind
    id: str
    title: str
    description: str = ""
    slug: str | None = None
    resource_type: str | None = None
    stage: str | None = None
    grade_min: int | None = None
    grade_max: int | None = None
    chapter_count: int | None = None
    target_version: str | None = None
    is_test_fixture: bool = False
    content_notice: str | None = None
    available: bool = True
    unavailable_reason: str | None = None
    route: str
    created_at: datetime | None = None
    is_bookmarked: bool = False


class PaginatedLearningItemsDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LearningItemDTO]
    total: int
    limit: int
    offset: int
    profile: str


class BookmarkDTO(LearningItemDTO):
    bookmarked_at: datetime


class PaginatedBookmarksDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BookmarkDTO]
    total: int
    limit: int
    offset: int
    profile: str


class OpenEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKind
    target_id: TargetId
    client_event_id: Annotated[
        str | None,
        StringConstraints(pattern=r"^[A-Za-z0-9._:-]{8,64}$", min_length=8, max_length=64),
    ] = None


class OpenEventReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID
    target_kind: TargetKind
    target_id: str
    title: str
    recorded_at: datetime
    duplicate: bool = False


class HistoryItemDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["READING", "OPEN"]
    target_kind: TargetKind
    target_id: str
    title: str
    description: str = ""
    chapter_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    revision: int | None = None
    revision_id: uuid.UUID | None = None
    event_kind: str | None = None
    section_key: str | None = None
    block_id: str | None = None
    target_version: str | None = None
    created_at: datetime
    is_current_revision: bool | None = None
    available: bool = True
    unavailable_reason: str | None = None
    route: str | None = None


class PaginatedHistoryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HistoryItemDTO]
    total: int
    limit: int
    offset: int


class ContinueItemDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: uuid.UUID
    course_id: uuid.UUID
    course_title: str
    chapter_title: str
    revision: int
    revision_id: uuid.UUID
    event_kind: str
    section_key: str | None = None
    block_id: str | None = None
    created_at: datetime
    is_current_revision: bool
    route: str


class ContinueDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: ContinueItemDTO | None


class PicturebookProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_index: StrictInt = Field(ge=0, le=2)


class PicturebookProgressDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    page_index: int
    updated_at: datetime | None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _picturebook_story_id(story_id: str) -> str:
    if story_id not in PICTUREBOOK_IDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="绘本不存在")
    return story_id


@router.get("/learning/picturebooks/{story_id}/progress", response_model=PicturebookProgressDTO)
async def read_picturebook_progress(
    story_id: str,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> PicturebookProgressDTO:
    story_id = _picturebook_story_id(story_id)
    row = await db.scalar(
        select(PicturebookProgress).where(
            PicturebookProgress.owner_user_id == context.user.id,
            PicturebookProgress.story_id == story_id,
        )
    )
    return PicturebookProgressDTO(
        story_id=story_id,
        page_index=row.page_index if row else 0,
        updated_at=row.updated_at if row else None,
    )


@router.put(
    "/learning/picturebooks/{story_id}/progress",
    response_model=PicturebookProgressDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def save_picturebook_progress(
    story_id: str,
    body: PicturebookProgressUpdate,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> PicturebookProgressDTO:
    story_id = _picturebook_story_id(story_id)
    statement = (
        pg_insert(PicturebookProgress)
        .values(
            owner_user_id=context.user.id,
            story_id=story_id,
            page_index=body.page_index,
        )
        .on_conflict_do_update(
            index_elements=["owner_user_id", "story_id"],
            set_={"page_index": body.page_index, "updated_at": func.now()},
        )
        .returning(PicturebookProgress.page_index, PicturebookProgress.updated_at)
    )
    page_index, updated_at = (await db.execute(statement)).one()
    await db.commit()
    return PicturebookProgressDTO(story_id=story_id, page_index=page_index, updated_at=updated_at)


async def _viewer(context: SessionContext, db: AsyncSession, settings: Settings) -> ViewerScope:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    return viewer_scope_from_profile(profile, settings)


def _profile(viewer: ViewerScope) -> str:
    return viewer.profile.value if hasattr(viewer.profile, "value") else str(viewer.profile)


def _route(kind: TargetKind, target_id: str) -> str:
    return {
        "COURSE": f"/courses/{target_id}",
        "RESOURCE": f"/resources/{target_id}",
        "ANIMATION": f"/animations/{target_id}",
    }[kind]


def _resource_route(resource_id: uuid.UUID, resource_kind: str) -> str:
    if resource_kind == "INTERACTIVE":
        return f"/interactive/{resource_id}"
    return _route("RESOURCE", str(resource_id))


def _not_visible() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习内容不可用")


def _resource_variant_available(variant: ResourceVariant, settings: Settings) -> bool:
    return store_for(settings).exists(variant.storage_key)


async def _resolve_visible_target(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    kind: TargetKind,
    target_id: str,
    settings: Settings,
    require_file: bool = True,
) -> dict[str, Any] | None:
    """Return a safe public target projection, or ``None`` when not visible."""

    if kind == "COURSE":
        try:
            parsed = uuid.UUID(target_id)
        except ValueError:
            return None
        item = await visible_course(db, course_id=parsed, viewer=viewer)
        if item is None:
            return None
        return {
            "kind": kind,
            "id": str(item.course_id),
            "title": item.title,
            "description": item.description,
            "slug": item.slug,
            "stage": viewer.stage.value if viewer.stage is not None else None,
            "chapter_count": len(item.chapters),
            "target_version": None,
            "is_test_fixture": any(chapter.is_test_fixture for chapter in item.chapters),
            "content_notice": next(
                (chapter.content_notice for chapter in item.chapters if chapter.content_notice),
                None,
            ),
            "route": _route(kind, str(item.course_id)),
        }

    if kind == "RESOURCE":
        try:
            parsed = uuid.UUID(target_id)
            resource = await load_visible_resource(db, viewer=viewer, resource_id=parsed)
            if resource.kind == "INTERACTIVE":
                revision = await db.scalar(
                    select(InteractiveRevision).where(
                        InteractiveRevision.id == resource.active_interactive_revision_id,
                        InteractiveRevision.resource_id == resource.id,
                    )
                )
                available = bool(
                    revision and store_for(settings).exists(revision.document_storage_key)
                )
                if require_file and not available:
                    return None
                return {
                    "kind": kind,
                    "id": str(resource.id),
                    "title": resource.title,
                    "description": resource.description,
                    "slug": resource.stable_slug,
                    "resource_type": resource.kind,
                    "stage": resource.stage,
                    "grade_min": resource.grade_min,
                    "grade_max": resource.grade_max,
                    "target_version": str(revision.id) if revision else None,
                    "is_test_fixture": resource.is_test_fixture,
                    "content_notice": (
                        "测试内容，未作人工教学审校" if resource.is_test_fixture else None
                    ),
                    "route": _resource_route(resource.id, resource.kind),
                    "has_available_content": available,
                }
            if require_file:
                item = await resource_detail(
                    db, viewer=viewer, resource_id=parsed, settings=settings
                )
            else:
                variants = await db.scalars(
                    select(ResourceVariant).where(ResourceVariant.resource_id == resource.id)
                )
                return {
                    "kind": kind,
                    "id": str(resource.id),
                    "title": resource.title,
                    "description": resource.description,
                    "slug": resource.stable_slug,
                    "resource_type": resource.kind,
                    "stage": resource.stage,
                    "grade_min": resource.grade_min,
                    "grade_max": resource.grade_max,
                    "target_version": (
                        resource.updated_at.isoformat() if resource.updated_at else None
                    ),
                    "is_test_fixture": resource.is_test_fixture,
                    "content_notice": "测试内容，未作人工教学审校"
                    if resource.is_test_fixture
                    else None,
                    "route": _resource_route(resource.id, resource.kind),
                    "has_available_content": any(
                        _resource_variant_available(variant, settings) for variant in variants
                    ),
                }
        except (ValueError, ResourceError):
            return None
        return {
            "kind": kind,
            "id": str(item.id),
            "title": item.title,
            "description": item.description,
            "slug": item.slug,
            "resource_type": item.kind,
            "stage": item.stage,
            "grade_min": item.grade_min,
            "grade_max": item.grade_max,
            "target_version": (resource.updated_at.isoformat() if resource.updated_at else None),
            "is_test_fixture": item.is_test_fixture,
            "content_notice": item.content_notice,
            "route": _resource_route(item.id, item.kind),
            "has_available_content": any(variant.available for variant in item.variants),
        }

    try:
        definition = await load_visible_animation(db, viewer=viewer, identifier=target_id)
    except AnimationError:
        return None
    public = public_definition(definition)
    return {
        "kind": kind,
        "id": str(public["id"]),
        "title": str(public.get("title") or public["id"]),
        "description": str(public.get("summary") or ""),
        "slug": str(public["id"]),
        "stage": public.get("stage"),
        "grade_min": public.get("grade_min"),
        "grade_max": public.get("grade_max"),
        "is_test_fixture": bool(public.get("is_test_fixture")),
        "content_notice": public.get("content_notice"),
        "target_version": str(public.get("chapter_revision") or "") or None,
        "route": _route(kind, str(public["id"])),
    }


def _item_projection(
    values: dict[str, Any], *, created_at: datetime | None = None
) -> LearningItemDTO:
    return LearningItemDTO(**{**values, "created_at": created_at})


async def _catalog_items(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    settings: Settings,
    q: str | None,
    kind: TargetKind | None,
    resource_type: str | None,
    topic: str | None,
    requested_stage: str | None,
) -> list[LearningItemDTO]:
    if requested_stage is not None and (
        viewer.stage is None or requested_stage != viewer.stage.value
    ):
        return []
    needle = q.casefold().strip() if q else None
    topic_needle = topic.casefold().strip() if topic else None
    items: list[LearningItemDTO] = []

    if kind in (None, "COURSE"):
        for course in await visible_courses(db, viewer):
            searchable = " ".join(
                (course.slug, course.title, course.topic, course.description)
            ).casefold()
            if needle and needle not in searchable:
                continue
            if topic_needle and topic_needle not in course.topic.casefold():
                continue
            values = {
                "kind": "COURSE",
                "id": str(course.course_id),
                "title": course.title,
                "description": course.description,
                "slug": course.slug,
                "stage": viewer.stage.value if viewer.stage is not None else None,
                "chapter_count": len(course.chapters),
                "is_test_fixture": any(ch.is_test_fixture for ch in course.chapters),
                "content_notice": next(
                    (ch.content_notice for ch in course.chapters if ch.content_notice), None
                ),
                "route": _route("COURSE", str(course.course_id)),
            }
            items.append(_item_projection(values))

    if kind in (None, "RESOURCE"):
        resource_items = await list_student_resources(
            db,
            viewer=viewer,
            kind=resource_type,
            settings=settings,
            limit=200,
        )
        for resource in resource_items.items:
            knowledge_names = list(
                await db.scalars(
                    select(KnowledgePoint.name)
                    .join(
                        ResourceKnowledgePoint,
                        ResourceKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
                    )
                    .where(ResourceKnowledgePoint.resource_id == resource.id)
                )
            )
            searchable = " ".join(
                (
                    resource.slug,
                    resource.title,
                    resource.description,
                    *resource.knowledge_point_slugs,
                    *knowledge_names,
                )
            ).casefold()
            if needle and needle not in searchable:
                continue
            if topic_needle and topic_needle not in searchable:
                continue
            values = {
                "kind": "RESOURCE",
                "id": str(resource.id),
                "title": resource.title,
                "description": resource.description,
                "slug": resource.slug,
                "resource_type": resource.kind,
                "stage": resource.stage,
                "grade_min": resource.grade_min,
                "grade_max": resource.grade_max,
                "is_test_fixture": resource.is_test_fixture,
                "content_notice": resource.content_notice,
                "route": _resource_route(resource.id, resource.kind),
            }
            items.append(_item_projection(values))

    if kind in (None, "ANIMATION"):
        for definition in await visible_animations(db, viewer=viewer):
            public = public_definition(definition)
            searchable = " ".join(
                (
                    str(public.get("id") or ""),
                    str(public.get("title") or ""),
                    str(public.get("summary") or ""),
                    *[str(value) for value in public.get("knowledge_points") or []],
                )
            ).casefold()
            if needle and needle not in searchable:
                continue
            if topic_needle and topic_needle not in searchable:
                continue
            identifier = str(public["id"])
            values = {
                "kind": "ANIMATION",
                "id": identifier,
                "title": str(public.get("title") or identifier),
                "description": str(public.get("summary") or ""),
                "slug": identifier,
                "stage": public.get("stage"),
                "grade_min": public.get("grade_min"),
                "grade_max": public.get("grade_max"),
                "is_test_fixture": bool(public.get("is_test_fixture")),
                "content_notice": public.get("content_notice"),
                "route": _route("ANIMATION", identifier),
            }
            items.append(_item_projection(values))

    items.sort(key=lambda item: (item.title.casefold(), item.kind, item.id))
    return items


def _paginate[T](items: list[T], *, limit: int, offset: int) -> tuple[list[T], int]:
    bounded_limit = max(1, min(limit, 100))
    bounded_offset = max(0, offset)
    return items[bounded_offset : bounded_offset + bounded_limit], len(items)


@router.get("/learning/catalog", response_model=PaginatedLearningItemsDTO)
async def learning_catalog(
    request: Request,
    q: str | None = Query(default=None, max_length=120),
    kind: TargetKind | None = Query(default=None),
    resource_type: str | None = Query(default=None, max_length=16),
    topic: str | None = Query(default=None, max_length=120),
    stage: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> PaginatedLearningItemsDTO:
    viewer = await _viewer(context, db, _settings(request))
    items = await _catalog_items(
        db,
        viewer=viewer,
        settings=_settings(request),
        q=q,
        kind=kind,
        resource_type=resource_type,
        topic=topic,
        requested_stage=stage,
    )
    bookmark_rows = list(
        await db.execute(
            select(LearningBookmark.target_kind, LearningBookmark.target_id).where(
                LearningBookmark.owner_user_id == context.user.id
            )
        )
    )
    bookmarked = {(str(row[0]), str(row[1])) for row in bookmark_rows}
    # The catalogue response carries the authoritative state for every item;
    # the UI does not need to infer it from a paginated bookshelf response.
    items = [
        item.model_copy(update={"is_bookmarked": (item.kind, item.id) in bookmarked})
        for item in items
    ]
    page, total = _paginate(items, limit=limit, offset=offset)
    return PaginatedLearningItemsDTO(
        items=page, total=total, limit=limit, offset=offset, profile=_profile(viewer)
    )


async def _bookmark_projection(
    db: AsyncSession,
    *,
    row: LearningBookmark,
    viewer: ViewerScope,
    settings: Settings,
) -> BookmarkDTO:
    kind = row.target_kind  # persisted values are constrained by the database
    target = await _resolve_visible_target(
        db,
        viewer=viewer,
        kind=kind,  # type: ignore[arg-type]
        target_id=row.target_id,
        settings=settings,
    )
    if target is None or (
        row.target_kind == "RESOURCE" and not target.get("has_available_content", False)
    ):
        return BookmarkDTO(
            kind=kind,  # type: ignore[arg-type]
            id=row.target_id,
            title=row.target_title,
            resource_type=row.target_type,
            available=False,
            unavailable_reason="CONTENT_NOT_VISIBLE",
            route=_route(kind, row.target_id),  # type: ignore[arg-type]
            bookmarked_at=row.created_at,
            is_bookmarked=True,
        )
    return BookmarkDTO(**target, bookmarked_at=row.created_at, is_bookmarked=True)


@router.get("/learning/bookshelf", response_model=PaginatedBookmarksDTO)
async def learning_bookshelf(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> PaginatedBookmarksDTO:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(LearningBookmark)
            .where(LearningBookmark.owner_user_id == context.user.id)
        )
        or 0
    )
    rows = list(
        await db.scalars(
            select(LearningBookmark)
            .where(LearningBookmark.owner_user_id == context.user.id)
            .order_by(LearningBookmark.created_at.desc(), LearningBookmark.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    items = [
        await _bookmark_projection(db, row=row, viewer=viewer, settings=settings) for row in rows
    ]
    return PaginatedBookmarksDTO(
        items=items, total=total, limit=limit, offset=offset, profile=_profile(viewer)
    )


@router.put(
    "/learning/bookshelf/{target_kind}/{target_id}",
    response_model=BookmarkDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def add_bookmark(
    target_kind: TargetKind,
    target_id: TargetId,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> BookmarkDTO:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    target = await _resolve_visible_target(
        db,
        viewer=viewer,
        kind=target_kind,
        target_id=target_id,
        settings=settings,
    )
    if target is None:
        raise _not_visible()
    existing = await db.scalar(
        select(LearningBookmark).where(
            LearningBookmark.owner_user_id == context.user.id,
            LearningBookmark.target_kind == target_kind,
            LearningBookmark.target_id == target_id,
        )
    )
    if existing is None:
        existing = LearningBookmark(
            owner_user_id=context.user.id,
            target_kind=target_kind,
            target_id=target_id,
            target_title=target["title"],
            target_type=target.get("resource_type"),
        )
        db.add(existing)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(LearningBookmark).where(
                    LearningBookmark.owner_user_id == context.user.id,
                    LearningBookmark.target_kind == target_kind,
                    LearningBookmark.target_id == target_id,
                )
            )
            if existing is None:  # pragma: no cover - unexpected constraint failure
                raise
    return BookmarkDTO(**target, bookmarked_at=existing.created_at, is_bookmarked=True)


@router.delete(
    "/learning/bookshelf/{target_kind}/{target_id}",
    dependencies=[Depends(csrf_dependency)],
)
async def remove_bookmark(
    target_kind: TargetKind,
    target_id: TargetId,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    row = await db.scalar(
        select(LearningBookmark).where(
            LearningBookmark.owner_user_id == context.user.id,
            LearningBookmark.target_kind == target_kind,
            LearningBookmark.target_id == target_id,
        )
    )
    deleted = row is not None
    if row is not None:
        await db.delete(row)
        await db.commit()
    return {"deleted": deleted}


@router.post(
    "/learning/open-events",
    response_model=OpenEventReceipt,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def record_open_event(
    payload: OpenEventRequest,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> OpenEventReceipt:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    if payload.client_event_id:
        existing = await db.scalar(
            select(LearningOpenEvent).where(
                LearningOpenEvent.owner_user_id == context.user.id,
                LearningOpenEvent.client_event_id == payload.client_event_id,
            )
        )
        if existing is not None:
            if (
                existing.target_kind != payload.target_kind
                or existing.target_id != payload.target_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="OPEN_EVENT_IDEMPOTENCY_CONFLICT",
                )
            return OpenEventReceipt(
                event_id=existing.id,
                target_kind=existing.target_kind,  # type: ignore[arg-type]
                target_id=existing.target_id,
                title=existing.target_title,
                recorded_at=existing.created_at,
                duplicate=True,
            )
    target = await _resolve_visible_target(
        db,
        viewer=viewer,
        kind=payload.target_kind,
        target_id=payload.target_id,
        settings=settings,
        require_file=True,
    )
    if target is None:
        raise _not_visible()
    if payload.target_kind == "RESOURCE" and not target.get("has_available_content", False):
        # A missing file is not an explicit successful open. Keep any bookmark
        # so the student can remove it, but do not create misleading history.
        raise _not_visible()
    now = datetime.now(UTC)
    event = LearningOpenEvent(
        owner_user_id=context.user.id,
        client_event_id=payload.client_event_id,
        target_kind=payload.target_kind,
        target_id=payload.target_id,
        target_title=target["title"],
        target_version=target.get("target_version"),
        created_at=now,
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if payload.client_event_id:
            existing = await db.scalar(
                select(LearningOpenEvent).where(
                    LearningOpenEvent.owner_user_id == context.user.id,
                    LearningOpenEvent.client_event_id == payload.client_event_id,
                )
            )
            if existing is not None:
                if (
                    existing.target_kind != payload.target_kind
                    or existing.target_id != payload.target_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="OPEN_EVENT_IDEMPOTENCY_CONFLICT",
                    ) from None
                return OpenEventReceipt(
                    event_id=existing.id,
                    target_kind=existing.target_kind,  # type: ignore[arg-type]
                    target_id=existing.target_id,
                    title=existing.target_title,
                    recorded_at=existing.created_at,
                    duplicate=True,
                )
        raise
    return OpenEventReceipt(
        event_id=event.id,
        target_kind=payload.target_kind,
        target_id=payload.target_id,
        title=target["title"],
        recorded_at=event.created_at,
        duplicate=False,
    )


async def _reading_history_rows(
    db: AsyncSession, *, owner_user_id: uuid.UUID, viewer: ViewerScope
) -> list[HistoryItemDTO]:
    events = list(
        await db.scalars(
            select(ReadingEvent)
            .where(ReadingEvent.user_id == owner_user_id)
            .order_by(ReadingEvent.created_at.desc(), ReadingEvent.id.desc())
            .limit(500)
        )
    )
    # Keep one useful recent row per chapter. A locationless ENTER/LEAVE can
    # appear only when that chapter has no locator-bearing event at all.
    chosen: dict[uuid.UUID, ReadingEvent] = {}
    for event in events:
        current = chosen.get(event.chapter_id)
        if current is None:
            chosen[event.chapter_id] = event
        elif (
            current.block_id is None
            and current.section_key is None
            and (event.block_id is not None or event.section_key is not None)
        ):
            chosen[event.chapter_id] = event

    output: list[HistoryItemDTO] = []
    for event in chosen.values():
        detail = await visible_chapter_detail(db, chapter_id=event.chapter_id, viewer=viewer)
        if detail is None:
            continue
        event_revision = await db.scalar(
            select(ChapterRevision.revision).where(ChapterRevision.id == event.revision_id)
        )
        if event_revision is None:
            continue
        historical_detail = await visible_chapter_detail(
            db,
            chapter_id=event.chapter_id,
            viewer=viewer,
            revision=event_revision,
        )
        route_revision = event_revision if historical_detail is not None else detail.revision
        route = f"/chapters/{event.chapter_id}?revision={route_revision}"
        if event.block_id:
            route += f"#{event.block_id}"
        output.append(
            HistoryItemDTO(
                kind="READING",
                target_kind="COURSE",
                target_id=str(detail.course_id),
                title=detail.title,
                description=f"{detail.course_title} · {detail.title}",
                chapter_id=detail.chapter_id,
                course_id=detail.course_id,
                revision=event_revision,
                revision_id=event.revision_id,
                event_kind=event.event_kind,
                section_key=event.section_key,
                block_id=event.block_id,
                created_at=event.created_at,
                is_current_revision=event.revision_id == detail.revision_id,
                route=route,
            )
        )
    return output


async def _open_history_rows(
    db: AsyncSession, *, owner_user_id: uuid.UUID, viewer: ViewerScope, settings: Settings
) -> list[HistoryItemDTO]:
    events = list(
        await db.scalars(
            select(LearningOpenEvent)
            .where(LearningOpenEvent.owner_user_id == owner_user_id)
            .order_by(LearningOpenEvent.created_at.desc(), LearningOpenEvent.id.desc())
            .limit(500)
        )
    )
    output: list[HistoryItemDTO] = []
    for event in events:
        target = await _resolve_visible_target(
            db,
            viewer=viewer,
            kind=event.target_kind,  # type: ignore[arg-type]
            target_id=event.target_id,
            settings=settings,
            require_file=False,
        )
        output.append(
            HistoryItemDTO(
                kind="OPEN",
                target_kind=event.target_kind,  # type: ignore[arg-type]
                target_id=event.target_id,
                title=target["title"] if target else event.target_title,
                description=target.get("description", "") if target else "",
                target_version=event.target_version,
                created_at=event.created_at,
                available=target is not None,
                unavailable_reason=None if target else "CONTENT_NOT_VISIBLE",
                route=target.get("route") if target else _route(event.target_kind, event.target_id),  # type: ignore[arg-type]
            )
        )
    return output


@router.get("/learning/history", response_model=PaginatedHistoryDTO)
async def learning_history(
    request: Request,
    kind: HistoryKind | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> PaginatedHistoryDTO:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    reading = (
        []
        if kind == "OPEN"
        else await _reading_history_rows(db, owner_user_id=context.user.id, viewer=viewer)
    )
    opened = (
        []
        if kind == "READING"
        else await _open_history_rows(
            db, owner_user_id=context.user.id, viewer=viewer, settings=settings
        )
    )
    items = sorted(reading + opened, key=lambda item: item.created_at, reverse=True)
    page, total = _paginate(items, limit=limit, offset=offset)
    return PaginatedHistoryDTO(items=page, total=total, limit=limit, offset=offset)


@router.get("/learning/continue", response_model=ContinueDTO)
async def continue_learning(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> ContinueDTO:
    viewer = await _viewer(context, db, _settings(request))
    events = list(
        await db.scalars(
            select(ReadingEvent)
            .where(
                ReadingEvent.user_id == context.user.id,
                or_(ReadingEvent.block_id.is_not(None), ReadingEvent.section_key.is_not(None)),
            )
            .order_by(ReadingEvent.created_at.desc(), ReadingEvent.id.desc())
            .limit(100)
        )
    )
    for event in events:
        detail = await visible_chapter_detail(db, chapter_id=event.chapter_id, viewer=viewer)
        if detail is None:
            continue
        revision = await db.scalar(
            select(ChapterRevision.revision).where(ChapterRevision.id == event.revision_id)
        )
        if revision is None:
            continue
        historical_detail = await visible_chapter_detail(
            db,
            chapter_id=event.chapter_id,
            viewer=viewer,
            revision=revision,
        )
        route_revision = revision if historical_detail is not None else detail.revision
        route = f"/chapters/{event.chapter_id}?revision={route_revision}"
        if event.block_id:
            route += f"#{event.block_id}"
        return ContinueDTO(
            item=ContinueItemDTO(
                chapter_id=event.chapter_id,
                course_id=detail.course_id,
                course_title=detail.course_title,
                chapter_title=detail.title,
                revision=revision,
                revision_id=event.revision_id,
                event_kind=event.event_kind,
                section_key=event.section_key,
                block_id=event.block_id,
                created_at=event.created_at,
                is_current_revision=event.revision_id == detail.revision_id,
                route=route,
            )
        )
    return ContinueDTO(item=None)


__all__ = ["router"]
