"""Stable HTTP contracts for admin packages and owner-scoped activities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.interactive.package import Manifest, PromptSpec, SceneSpec


class InteractiveManifestV1(Manifest):
    cover: str | None
    summary: str
    knowledge_points: list[str]
    capabilities: list[str]
    scenes: list[SceneSpec]
    prompts: list[PromptSpec]


class InteractiveVersionDTO(BaseModel):
    id: uuid.UUID
    resource_id: uuid.UUID
    revision: int
    manifest: InteractiveManifestV1
    capabilities: list[str]
    package_sha256: str
    validation_report: dict[str, Any]
    locked: bool
    created_at: datetime | None


class InteractiveVersionsDTO(BaseModel):
    items: list[InteractiveVersionDTO]
    active_revision_id: uuid.UUID | None


class InteractiveAdminListItemDTO(BaseModel):
    id: uuid.UUID
    title: str
    stage: str
    purpose: str
    subject: str
    publication_status: str
    review_status: str
    active_revision: int | None
    validation_report: dict[str, Any] | None
    scene_capability_declared: bool
    checkpoint_capability_declared: bool
    updated_at: datetime | None


class InteractiveAdminListDTO(BaseModel):
    items: list[InteractiveAdminListItemDTO]


class InteractiveCatalogItemDTO(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    purpose: Literal["LESSON", "GAME", "EXPERIMENT"]
    subject: str
    stage: str
    grade_min: int | None
    grade_max: int | None
    knowledge_points: list[str]
    cover: str | None
    revision: int
    capabilities: list[str]
    is_test_fixture: bool
    local_demo_visible: bool = False
    chapter_revision_ids: list[uuid.UUID] = Field(default_factory=list)
    activity_status: Literal["NOT_STARTED", "ACTIVE", "COMPLETED", "ABANDONED"]
    can_resume: bool
    session_id: uuid.UUID | None


class InteractiveCatalogDTO(BaseModel):
    items: list[InteractiveCatalogItemDTO]
    stage: str


class InteractiveContentDTO(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    purpose: Literal["LESSON", "GAME", "EXPERIMENT"]
    subject: str
    revision_id: uuid.UUID
    revision: int
    manifest: InteractiveManifestV1


class InteractiveSessionDTO(BaseModel):
    id: uuid.UUID
    resource_id: uuid.UUID
    revision_id: uuid.UUID
    stage: str
    status: Literal["ACTIVE", "COMPLETED", "ABANDONED"]
    base_revision: int
    current_scene_id: str | None
    game_state: dict[str, Any]
    host_state: dict[str, Any]
    game_result: dict[str, Any] | None
    completion_source: str | None
    created_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    resource_title: str | None = None
    resource_available: bool | None = None


class InteractiveSessionDetailDTO(BaseModel):
    session: InteractiveSessionDTO
    resource: InteractiveResourceRefDTO
    manifest: InteractiveManifestV1


class InteractiveResourceRefDTO(BaseModel):
    id: uuid.UUID
    title: str
    purpose: Literal["LESSON", "GAME", "EXPERIMENT"]
    subject: str


class InteractiveDocumentDTO(BaseModel):
    session_id: uuid.UUID
    revision_id: uuid.UUID
    document_html: str
    manifest: InteractiveManifestV1


class InteractiveHistoryDTO(BaseModel):
    items: list[InteractiveSessionDTO]


class InteractivePreviewDTO(BaseModel):
    revision_id: uuid.UUID
    resource_id: uuid.UUID
    manifest: InteractiveManifestV1
    document_html: str
    preview: Literal[True]


__all__ = [name for name in globals() if name.startswith("Interactive")]
