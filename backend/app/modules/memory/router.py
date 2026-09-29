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
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_student
from app.modules.memory.service import (
    MemoryDocumentNotFound,
    MemoryDocumentRevisionConflict,
    MemoryDocumentValidation,
    MemoryForgotten,
    MemoryNotFound,
    MemoryRevisionConflict,
    MemoryTransitionInvalid,
    apply_memory_event,
    create_document,
    delete_document,
    get_document,
    get_document_version,
    list_document_versions,
    list_documents,
    list_memories,
    memory_detail,
    restore_document,
    update_document,
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


_DOCUMENT_CATEGORIES = Literal["PREFERENCE", "GOAL", "INTEREST", "NOTE"]


class MemoryDocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    category: _DOCUMENT_CATEGORIES = "NOTE"
    content_markdown: str = Field(default="", max_length=20_000)
    ai_enabled: bool = False
    is_primary: bool = False


class MemoryDocumentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=80)
    category: _DOCUMENT_CATEGORIES | None = None
    content_markdown: str | None = Field(default=None, max_length=20_000)
    ai_enabled: bool | None = None


class MemoryDocumentRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_revision: int = Field(
        ge=1,
        validation_alias=AliasChoices("version_revision", "revision"),
    )
    base_revision: int = Field(ge=1)


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


@router.get("/growth/documents")
async def read_documents(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"items": await list_documents(db, owner_user_id=context.user.id)}


@router.post("/growth/documents", dependencies=[Depends(csrf_dependency)])
async def write_document(
    body: MemoryDocumentCreateRequest,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await create_document(
            db,
            owner_user_id=context.user.id,
            title=body.title,
            category=body.category,
            content_markdown=body.content_markdown,
            ai_enabled=body.ai_enabled,
            is_primary=body.is_primary,
        )
    except MemoryDocumentValidation as caught:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(caught)
        ) from caught


@router.get("/growth/documents/{document_id}")
async def read_document(
    document_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await get_document(db, owner_user_id=context.user.id, document_id=document_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return result


@router.patch("/growth/documents/{document_id}", dependencies=[Depends(csrf_dependency)])
async def edit_document(
    document_id: uuid.UUID,
    body: MemoryDocumentUpdateRequest,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await update_document(
            db,
            owner_user_id=context.user.id,
            document_id=document_id,
            base_revision=body.base_revision,
            title=body.title,
            category=body.category,
            content_markdown=body.content_markdown,
            ai_enabled=body.ai_enabled,
        )
    except MemoryDocumentNotFound as caught:
        _document_raise(status.HTTP_404_NOT_FOUND, str(caught))
    except MemoryDocumentRevisionConflict as caught:
        _document_raise(status.HTTP_409_CONFLICT, str(caught))
    except MemoryDocumentValidation as caught:
        _document_raise(status.HTTP_422_UNPROCESSABLE_ENTITY, str(caught))


@router.get("/growth/documents/{document_id}/versions")
async def read_document_versions(
    document_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return {
            "items": await list_document_versions(
                db, owner_user_id=context.user.id, document_id=document_id
            )
        }
    except MemoryDocumentNotFound as caught:
        _document_raise(status.HTTP_404_NOT_FOUND, str(caught))


@router.get("/growth/documents/{document_id}/versions/{revision}")
async def read_document_version(
    document_id: uuid.UUID,
    revision: int,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await get_document_version(
            db,
            owner_user_id=context.user.id,
            document_id=document_id,
            revision=revision,
        )
    except MemoryDocumentNotFound as caught:
        _document_raise(status.HTTP_404_NOT_FOUND, str(caught))


@router.post("/growth/documents/{document_id}/restore", dependencies=[Depends(csrf_dependency)])
async def restore_memory_document(
    document_id: uuid.UUID,
    body: MemoryDocumentRestoreRequest,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await restore_document(
            db,
            owner_user_id=context.user.id,
            document_id=document_id,
            version_revision=body.version_revision,
            base_revision=body.base_revision,
        )
    except MemoryDocumentNotFound as caught:
        _document_raise(status.HTTP_404_NOT_FOUND, str(caught))
    except MemoryDocumentRevisionConflict as caught:
        _document_raise(status.HTTP_409_CONFLICT, str(caught))


@router.delete("/growth/documents/{document_id}", dependencies=[Depends(csrf_dependency)])
async def remove_document(
    document_id: uuid.UUID,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    try:
        await delete_document(db, owner_user_id=context.user.id, document_id=document_id)
    except MemoryDocumentNotFound as caught:
        _document_raise(status.HTTP_404_NOT_FOUND, str(caught))
    return {"deleted": True}


def _raise(code: str, detail: str) -> None:
    raise HTTPException(
        status_code=_CODE_STATUS.get(code, status.HTTP_409_CONFLICT), detail=f"{code}: {detail}"
    )


def _document_raise(code: int, detail: str) -> None:
    raise HTTPException(status_code=code, detail=detail)
