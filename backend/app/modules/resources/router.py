"""Resource API: student entry, real download/playback, admin registration.

Student routes resolve the viewer from the server-side session (T05) and run
the same visibility filter as the service layer, so an unpublished, withdrawn,
wrong-stage or cross-owner resource cannot be reached by guessing an id.

Admin routes require the admin role server-side. Uploads are raw request
bodies (no multipart dependency) so the configured size limit is enforced while
streaming, before anything is written into the store.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.database import get_session
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import viewer_scope_from_profile
from app.modules.identity.dependencies import (
    SessionContext,
    csrf_dependency,
    require_admin,
    require_student,
)
from app.modules.identity.models import LearnerProfile
from app.modules.resources.models import Resource, ResourceVariant
from app.modules.resources.schemas import (
    ResourceCreateRequest,
    ResourceListDTO,
    ResourcePatchRequest,
    ResourceSummaryDTO,
    ResourceTicketDTO,
    ResourceUploadReceipt,
)
from app.modules.resources.service import (
    ResourceError,
    consume_ticket,
    create_resource,
    issue_ticket,
    list_student_resources,
    patch_resource,
    resolve_variant,
    resource_detail,
    resource_summary,
    security_headers,
    stage_upload,
    store_for,
    store_variant,
)

router = APIRouter(tags=["resources"])
admin_router = APIRouter(tags=["resources-admin"])

SOURCE_OR_PREVIEW = Query(pattern="^(SOURCE|PREVIEW)$")


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _raise(error: ResourceError) -> None:
    raise HTTPException(status_code=error.status_code, detail=f"{error.code}: {error.message}")


async def _viewer(context: SessionContext, db: AsyncSession, settings: Settings) -> ViewerScope:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == context.user.id)
    )
    return viewer_scope_from_profile(profile, settings)


def _file_response(variant: ResourceVariant, path, *, inline: bool) -> FileResponse:
    """Real bytes with no same-origin execution and no cache of stale links.

    ``FileResponse`` keeps HTTP range support, which the video element needs to
    seek and to report ``loadeddata``/``ended`` truthfully.
    """

    headers = security_headers(variant, inline=inline)
    disposition = headers.pop("Content-Disposition")
    inline_ok = "inline" in disposition
    return FileResponse(
        path,
        media_type=variant.detected_mime,
        headers=headers,
        filename=variant.original_filename,
        content_disposition_type="inline" if inline_ok else "attachment",
    )


# --------------------------------------------------------------------------- #
# student
# --------------------------------------------------------------------------- #
@router.get("/resources", response_model=ResourceListDTO)
async def list_resources(
    request: Request,
    chapter_revision_id: uuid.UUID | None = Query(default=None),
    kind: str | None = Query(default=None),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> ResourceListDTO:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    return await list_student_resources(
        db,
        viewer=viewer,
        chapter_revision_id=chapter_revision_id,
        kind=kind,
        settings=settings,
    )


@router.get("/resources/{resource_id}", response_model=ResourceSummaryDTO)
async def read_resource(
    resource_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> ResourceSummaryDTO:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    try:
        return await resource_detail(db, viewer=viewer, resource_id=resource_id, settings=settings)
    except ResourceError as error:
        _raise(error)


@router.get("/resources/{resource_id}/content")
async def read_resource_content(
    resource_id: uuid.UUID,
    request: Request,
    variant: Annotated[str, SOURCE_OR_PREVIEW] = "SOURCE",
    disposition: str = Query(default="inline", pattern="^(inline|attachment)$"),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    try:
        _resource, row, path = await resolve_variant(
            db, viewer=viewer, resource_id=resource_id, variant=variant, settings=settings
        )
    except ResourceError as error:
        _raise(error)
    return _file_response(row, path, inline=disposition == "inline")


@router.post(
    "/resources/{resource_id}/tickets",
    response_model=ResourceTicketDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def create_resource_ticket(
    resource_id: uuid.UUID,
    request: Request,
    variant: Annotated[str, SOURCE_OR_PREVIEW] = "SOURCE",
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> ResourceTicketDTO:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    try:
        return await issue_ticket(
            db,
            viewer=viewer,
            owner_user_id=context.user.id,
            resource_id=resource_id,
            variant=variant,
            settings=settings,
        )
    except ResourceError as error:
        _raise(error)


@router.get("/resources/content/{token}")
async def read_resource_by_ticket(
    token: str,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    settings = _settings(request)
    viewer = await _viewer(context, db, settings)
    try:
        _resource, row, path = await consume_ticket(
            db,
            viewer=viewer,
            owner_user_id=context.user.id,
            token=token,
            settings=settings,
        )
    except ResourceError as error:
        _raise(error)
    return _file_response(row, path, inline=row.detected_mime.startswith("video/"))


# --------------------------------------------------------------------------- #
# admin
# --------------------------------------------------------------------------- #
@admin_router.get("/admin/resources", response_model=ResourceListDTO)
async def admin_list_resources(
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ResourceListDTO:
    settings = _settings(request)
    rows = list(await db.scalars(select(Resource).order_by(Resource.stable_slug)))
    return ResourceListDTO(
        items=[await resource_summary(db, row, settings=settings) for row in rows],
        profile=settings.app_env,
    )


@admin_router.post(
    "/admin/resources",
    response_model=ResourceSummaryDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_create_resource(
    payload: ResourceCreateRequest,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ResourceSummaryDTO:
    try:
        resource = await create_resource(db, actor=context.user, payload=payload)
    except ResourceError as error:
        _raise(error)
    return await resource_summary(db, resource, settings=_settings(request))


@admin_router.patch(
    "/admin/resources/{resource_id}",
    response_model=ResourceSummaryDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_patch_resource(
    resource_id: uuid.UUID,
    payload: ResourcePatchRequest,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ResourceSummaryDTO:
    resource = await db.scalar(select(Resource).where(Resource.id == resource_id))
    if resource is None:
        raise HTTPException(status_code=404, detail="RESOURCE_NOT_FOUND: 资源不存在")
    try:
        await patch_resource(db, actor=context.user, resource=resource, payload=payload)
    except ResourceError as error:
        _raise(error)
    return await resource_summary(db, resource, settings=_settings(request))


@admin_router.put(
    "/admin/resources/{resource_id}/content",
    response_model=ResourceUploadReceipt,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_upload_content(
    resource_id: uuid.UUID,
    request: Request,
    variant: Annotated[str, SOURCE_OR_PREVIEW] = "SOURCE",
    x_filename: Annotated[str | None, Header(alias="X-Filename")] = None,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> ResourceUploadReceipt:
    settings = _settings(request)
    resource = await db.scalar(select(Resource).where(Resource.id == resource_id))
    if resource is None:
        raise HTTPException(status_code=404, detail="RESOURCE_NOT_FOUND: 资源不存在")
    store = store_for(settings)
    try:
        staged, size_bytes, sha256 = await stage_upload(
            store, request.stream(), max_bytes=settings.resource_upload_max_bytes
        )
        return await store_variant(
            db,
            actor=context.user,
            resource=resource,
            variant=variant,
            staged=staged,
            size_bytes=size_bytes,
            sha256=sha256,
            filename=x_filename,
            declared_mime=request.headers.get("content-type"),
            settings=settings,
        )
    except ResourceError as error:
        _raise(error)


__all__ = ["admin_router", "router"]
