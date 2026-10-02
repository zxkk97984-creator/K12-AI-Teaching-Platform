"""Admin authoring and owner-scoped student interaction APIs."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.content.service import viewer_scope_from_profile
from app.modules.identity.dependencies import (
    SessionContext,
    csrf_dependency,
    require_admin,
    require_student,
)
from app.modules.identity.models import LearnerProfile
from app.modules.interactive.models import InteractiveFile, InteractiveRevision, InteractiveSession
from app.modules.interactive.schemas import (
    InteractiveAdminListDTO,
    InteractiveCatalogDTO,
    InteractiveContentDTO,
    InteractiveDocumentDTO,
    InteractiveHistoryDTO,
    InteractivePreviewDTO,
    InteractiveSessionDetailDTO,
    InteractiveSessionDTO,
    InteractiveVersionDTO,
    InteractiveVersionsDTO,
)
from app.modules.interactive.service import (
    InteractiveError,
    _session_public,
    activate_version,
    add_prompt_audio,
    catalog,
    clone_draft,
    list_versions,
    owned_session,
    save_event,
    start_session,
    update_draft,
    upload_revision,
    visible_resource,
)
from app.modules.resources.models import Resource
from app.modules.resources.service import store_for

router = APIRouter(tags=["interactive"])
admin_router = APIRouter(tags=["interactive-admin"])


@admin_router.get("/admin/interactive/resources", response_model=InteractiveAdminListDTO)
async def admin_interactive_overview(
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    resources = list(
        await db.scalars(
            select(Resource)
            .where(Resource.kind == "INTERACTIVE")
            .order_by(Resource.updated_at.desc())
            .limit(200)
        )
    )
    items: list[dict[str, Any]] = []
    for resource in resources:
        revision = (
            await db.scalar(
                select(InteractiveRevision).where(
                    InteractiveRevision.id == resource.active_interactive_revision_id
                )
            )
            if resource.active_interactive_revision_id
            else None
        )
        capabilities = set(revision.capabilities) if revision else set()
        items.append(
            {
                "id": str(resource.id),
                "title": resource.title,
                "stage": resource.stage,
                "purpose": resource.interactive_purpose,
                "subject": resource.interactive_subject,
                "publication_status": resource.publication_status,
                "review_status": resource.review_status,
                "active_revision": revision.revision if revision else None,
                "validation_report": revision.validation_report if revision else None,
                "scene_capability_declared": "SCENES" in capabilities,
                "checkpoint_capability_declared": "CHECKPOINTS" in capabilities,
                "updated_at": resource.updated_at,
            }
        )
    return {"items": items}


def fail(error: InteractiveError) -> None:
    raise HTTPException(
        status_code=error.status_code, detail=f"{error.code}: {error.message}"
    ) from error


async def viewer_for(request: Request, db: AsyncSession, user_id: uuid.UUID):
    profile = await db.scalar(select(LearnerProfile).where(LearnerProfile.user_id == user_id))
    if profile is None or not profile.stage:
        raise HTTPException(status_code=409, detail="STAGE_REQUIRED: 请先设置学段")
    return viewer_scope_from_profile(profile, request.app.state.settings)


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: uuid.UUID
    restart: bool = False


class ActivityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    event_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    scene_id: str | None = Field(default=None, max_length=100)
    game_state: dict[str, Any] | None = None
    playback_step: int | None = Field(default=None, ge=0)


class ActivityComplete(ActivityPatch):
    game_result: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="SDK_REPORTED", pattern=r"^(SDK_REPORTED|USER_CONFIRMED)$")


async def raw_upload(request: Request, limit: int) -> bytes:
    chunks: list[bytes] = []
    count = 0
    async for chunk in request.stream():
        count += len(chunk)
        if count > limit:
            raise HTTPException(status_code=413, detail="上传文件超过大小上限")
        chunks.append(chunk)
    if count == 0:
        raise HTTPException(status_code=422, detail="文件为空")
    return b"".join(chunks)


@admin_router.get(
    "/admin/resources/{resource_id}/interactive-revisions",
    response_model=InteractiveVersionsDTO,
)
async def admin_versions(
    resource_id: uuid.UUID,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    resource = await db.scalar(
        select(Resource).where(Resource.id == resource_id, Resource.kind == "INTERACTIVE")
    )
    if resource is None:
        raise HTTPException(status_code=404, detail="互动资源不存在")
    return {
        "items": await list_versions(db, resource_id=resource_id),
        "active_revision_id": str(resource.active_interactive_revision_id)
        if resource.active_interactive_revision_id
        else None,
    }


@admin_router.post(
    "/admin/resources/{resource_id}/interactive-revisions",
    response_model=InteractiveVersionDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_upload_version(
    resource_id: uuid.UUID,
    request: Request,
    x_filename: str = Header(default="index.html", alias="X-Filename"),
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    raw = await raw_upload(request, request.app.state.settings.resource_upload_max_bytes)
    try:
        return await upload_revision(
            db,
            resource_id=resource_id,
            actor=context.user,
            raw=raw,
            filename=x_filename,
            settings=request.app.state.settings,
        )
    except InteractiveError as caught:
        fail(caught)


@admin_router.patch(
    "/admin/resources/{resource_id}/interactive-revisions/{revision_id}",
    response_model=InteractiveVersionDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_update_version(
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    manifest: dict[str, Any],
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    try:
        return await update_draft(
            db, resource_id=resource_id, revision_id=revision_id, manifest_data=manifest
        )
    except InteractiveError as caught:
        fail(caught)


@admin_router.put(
    "/admin/resources/{resource_id}/interactive-revisions/{revision_id}/audio/{prompt_id}",
    response_model=InteractiveVersionDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_prompt_audio(
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    prompt_id: str,
    request: Request,
    x_filename: str = Header(default="prompt.mp3", alias="X-Filename"),
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    raw = await raw_upload(request, 5 * 1024 * 1024)
    try:
        return await add_prompt_audio(
            db,
            resource_id=resource_id,
            revision_id=revision_id,
            prompt_id=prompt_id,
            filename=x_filename,
            raw=raw,
            settings=request.app.state.settings,
        )
    except InteractiveError as caught:
        fail(caught)


@admin_router.post(
    "/admin/resources/{resource_id}/interactive-revisions/{revision_id}/activate",
    response_model=InteractiveVersionDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_activate(
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    try:
        return await activate_version(
            db,
            resource_id=resource_id,
            revision_id=revision_id,
            settings=request.app.state.settings,
        )
    except InteractiveError as caught:
        fail(caught)


@admin_router.post(
    "/admin/resources/{resource_id}/interactive-revisions/{revision_id}/clone",
    response_model=InteractiveVersionDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def admin_clone(
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await clone_draft(
            db,
            resource_id=resource_id,
            revision_id=revision_id,
            actor=context.user,
            settings=request.app.state.settings,
        )
    except InteractiveError as caught:
        fail(caught)


@admin_router.get(
    "/admin/resources/{resource_id}/interactive-revisions/{revision_id}/preview",
    response_model=InteractivePreviewDTO,
)
async def admin_preview(
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del context
    revision = await db.scalar(
        select(InteractiveRevision).where(
            InteractiveRevision.id == revision_id, InteractiveRevision.resource_id == resource_id
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    try:
        with store_for(request.app.state.settings).open(revision.document_storage_key) as stream:
            document = stream.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise HTTPException(status_code=503, detail="播放文档不可用") from None
    return {
        "revision_id": str(revision.id),
        "resource_id": str(resource_id),
        "manifest": revision.manifest,
        "document_html": document,
        "preview": True,
    }


@admin_router.get("/admin/resources/{resource_id}/interactive-revisions/{revision_id}/original")
async def admin_download_original(
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    del context
    revision = await db.scalar(
        select(InteractiveRevision).where(
            InteractiveRevision.id == revision_id,
            InteractiveRevision.resource_id == resource_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    store = store_for(request.app.state.settings)
    if not store.exists(revision.package_storage_key):
        raise HTTPException(status_code=503, detail="原始内容包不可用")
    suffix = ".zip" if revision.package_storage_key.endswith(".zip") else ".html"
    return FileResponse(
        store.resolve(revision.package_storage_key),
        media_type="application/zip" if suffix == ".zip" else "text/html",
        filename=f"interactive-{revision.revision}{suffix}",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


def private_file_response(file: InteractiveFile, settings: Any) -> FileResponse:
    return FileResponse(
        store_for(settings).resolve(file.storage_key),
        media_type=file.mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@admin_router.get(
    "/admin/resources/{resource_id}/interactive-revisions/{revision_id}/audio/{prompt_id}"
)
async def admin_audio_preview(
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    prompt_id: str,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    del context
    revision = await db.scalar(
        select(InteractiveRevision).where(
            InteractiveRevision.id == revision_id,
            InteractiveRevision.resource_id == resource_id,
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    prompt = next(
        (item for item in revision.manifest.get("prompts", []) if item.get("id") == prompt_id),
        None,
    )
    if not prompt or not prompt.get("audio"):
        raise HTTPException(status_code=404, detail="问题音频不存在")
    file = await db.scalar(
        select(InteractiveFile).where(
            InteractiveFile.revision_id == revision.id,
            InteractiveFile.relative_path == prompt["audio"],
        )
    )
    if file is None:
        raise HTTPException(status_code=404, detail="问题音频不存在")
    return private_file_response(file, request.app.state.settings)


@router.get("/interactive/resources", response_model=InteractiveCatalogDTO)
async def student_catalog(
    request: Request,
    purpose: str | None = Query(default=None, pattern=r"^(LESSON|GAME|EXPERIMENT)$"),
    q: str | None = Query(default=None, max_length=100),
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    return {
        "items": await catalog(
            db,
            viewer=viewer,
            owner_id=context.user.id,
            settings=request.app.state.settings,
            purpose=purpose,
            q=q,
        ),
        "stage": str(viewer.stage.value),
    }


@router.get("/interactive/resources/{resource_id}", response_model=InteractiveContentDTO)
async def student_content(
    resource_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        resource, revision = await visible_resource(
            db, resource_id=resource_id, viewer=viewer, settings=request.app.state.settings
        )
    except InteractiveError as caught:
        fail(caught)
    return {
        "id": str(resource.id),
        "title": resource.title,
        "description": resource.description,
        "purpose": resource.interactive_purpose,
        "subject": resource.interactive_subject,
        "revision_id": str(revision.id),
        "revision": revision.revision,
        "manifest": revision.manifest,
    }


@router.get("/interactive/resources/{resource_id}/cover")
async def student_cover(
    resource_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        _resource, revision = await visible_resource(
            db, resource_id=resource_id, viewer=viewer, settings=request.app.state.settings
        )
    except InteractiveError as caught:
        fail(caught)
    cover = revision.manifest.get("cover")
    if not cover:
        raise HTTPException(status_code=404, detail="封面不存在")
    file = await db.scalar(
        select(InteractiveFile).where(
            InteractiveFile.revision_id == revision.id,
            InteractiveFile.relative_path == cover,
        )
    )
    if file is None or not file.mime_type.startswith("image/"):
        raise HTTPException(status_code=404, detail="封面不存在")
    return private_file_response(file, request.app.state.settings)


@router.post(
    "/interactive/sessions",
    response_model=InteractiveSessionDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def begin_activity(
    body: SessionCreate,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        return await start_session(
            db,
            resource_id=body.resource_id,
            owner_id=context.user.id,
            viewer=viewer,
            settings=request.app.state.settings,
            restart=body.restart,
        )
    except InteractiveError as caught:
        fail(caught)


@router.get("/interactive/sessions", response_model=InteractiveHistoryDTO)
async def activity_history(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    rows = list(
        await db.scalars(
            select(InteractiveSession)
            .where(
                InteractiveSession.owner_user_id == context.user.id,
                InteractiveSession.stage == viewer.stage.value,
            )
            .order_by(InteractiveSession.created_at.desc())
            .limit(100)
        )
    )
    resource_ids = {row.resource_id for row in rows}
    resources = (
        {
            row.id: row
            for row in await db.scalars(select(Resource).where(Resource.id.in_(resource_ids)))
        }
        if resource_ids
        else {}
    )
    items = []
    for row in rows:
        item = _session_public(row)
        resource = resources.get(row.resource_id)
        item["resource_title"] = resource.title if resource else "已移除的互动内容"
        item["resource_available"] = bool(
            resource
            and resource.active_interactive_revision_id
            and (
                resource.publication_status == "PUBLISHED"
                or (
                    (resource.is_test_fixture or resource.local_demo_visible)
                    and resource.publication_status != "WITHDRAWN"
                    and request.app.state.settings.app_env != "production"
                )
            )
        )
        items.append(item)
    return {"items": items}


@router.get("/interactive/sessions/{session_id}", response_model=InteractiveSessionDetailDTO)
async def activity_detail(
    session_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        session, resource, version = await owned_session(
            db,
            session_id=session_id,
            owner_id=context.user.id,
            viewer=viewer,
            settings=request.app.state.settings,
        )
    except InteractiveError as caught:
        fail(caught)
    return {
        "session": _session_public(session),
        "resource": {
            "id": str(resource.id),
            "title": resource.title,
            "purpose": resource.interactive_purpose,
            "subject": resource.interactive_subject,
        },
        "manifest": version.manifest,
    }


@router.get("/interactive/sessions/{session_id}/document", response_model=InteractiveDocumentDTO)
async def activity_document(
    session_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        session, _resource, version = await owned_session(
            db,
            session_id=session_id,
            owner_id=context.user.id,
            viewer=viewer,
            settings=request.app.state.settings,
            active=True,
        )
    except InteractiveError as caught:
        fail(caught)
    try:
        with store_for(request.app.state.settings).open(version.document_storage_key) as stream:
            document = stream.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise HTTPException(status_code=503, detail="播放文档不可用") from None
    return {
        "session_id": str(session.id),
        "revision_id": str(version.id),
        "document_html": document,
        "manifest": version.manifest,
    }


@router.get("/interactive/sessions/{session_id}/audio/{prompt_id}")
async def activity_audio(
    session_id: uuid.UUID,
    prompt_id: str,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        _session, _resource, version = await owned_session(
            db,
            session_id=session_id,
            owner_id=context.user.id,
            viewer=viewer,
            settings=request.app.state.settings,
            active=True,
        )
    except InteractiveError as caught:
        fail(caught)
    prompt = next(
        (item for item in version.manifest.get("prompts", []) if item.get("id") == prompt_id), None
    )
    if not prompt or not prompt.get("audio"):
        raise HTTPException(status_code=404, detail="问题音频不存在")
    file = await db.scalar(
        select(InteractiveFile).where(
            InteractiveFile.revision_id == version.id,
            InteractiveFile.relative_path == prompt["audio"],
        )
    )
    if file is None:
        raise HTTPException(status_code=404, detail="问题音频不存在")
    return private_file_response(file, request.app.state.settings)


@router.patch(
    "/interactive/sessions/{session_id}/checkpoint",
    response_model=InteractiveSessionDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def activity_checkpoint(
    session_id: uuid.UUID,
    body: ActivityPatch,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        session, _resource, revision = await owned_session(
            db,
            session_id=session_id,
            owner_id=context.user.id,
            viewer=viewer,
            settings=request.app.state.settings,
        )
        return await save_event(
            db,
            session=session,
            revision=revision,
            owner_id=context.user.id,
            event_id=body.event_id,
            base_revision=body.base_revision,
            kind="CHECKPOINT",
            playback_step=body.playback_step,
            game_state=body.game_state,
            scene_id=body.scene_id,
        )
    except InteractiveError as caught:
        fail(caught)


@router.post(
    "/interactive/sessions/{session_id}/complete",
    response_model=InteractiveSessionDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def activity_complete(
    session_id: uuid.UUID,
    body: ActivityComplete,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        session, _resource, revision = await owned_session(
            db,
            session_id=session_id,
            owner_id=context.user.id,
            viewer=viewer,
            settings=request.app.state.settings,
        )
        return await save_event(
            db,
            session=session,
            revision=revision,
            owner_id=context.user.id,
            event_id=body.event_id,
            base_revision=body.base_revision,
            kind="COMPLETE",
            game_state=body.game_state,
            scene_id=body.scene_id,
            game_result=body.game_result,
            source=body.source,
        )
    except InteractiveError as caught:
        fail(caught)


class ActivityViewed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=0)
    event_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")


@router.post(
    "/interactive/sessions/{session_id}/viewed",
    response_model=InteractiveSessionDTO,
    dependencies=[Depends(csrf_dependency)],
)
async def activity_viewed(
    session_id: uuid.UUID,
    body: ActivityViewed,
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await viewer_for(request, db, context.user.id)
    try:
        session, _resource, revision = await owned_session(
            db,
            session_id=session_id,
            owner_id=context.user.id,
            viewer=viewer,
            settings=request.app.state.settings,
        )
        return await save_event(
            db,
            session=session,
            revision=revision,
            owner_id=context.user.id,
            event_id=body.event_id,
            base_revision=body.base_revision,
            kind="VIEWED",
        )
    except InteractiveError as caught:
        fail(caught)
