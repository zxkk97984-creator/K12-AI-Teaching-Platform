"""Pydantic DTOs for the resource registry.

Student DTOs never expose ``storage_key``, filesystem paths or the signed
ticket payload; they only describe what the student is allowed to open.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResourceKindLiteral = Literal["WORD", "SLIDES", "VIDEO", "PDF", "IMAGE", "INTERACTIVE"]
VariantLiteral = Literal["SOURCE", "PREVIEW"]


class ResourceVariantDTO(BaseModel):
    """One stored file, described without its internal storage key."""

    variant: VariantLiteral
    filename: str
    mime: str
    size_bytes: int
    sha256: str
    inline_ok: bool
    available: bool
    unavailable_reason: str | None


class ResourceSummaryDTO(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    kind: ResourceKindLiteral
    interactive_purpose: Literal["LESSON", "GAME", "EXPERIMENT"] | None = None
    interactive_subject: str | None = None
    active_interactive_revision_id: uuid.UUID | None = None
    stage: str
    grade_min: int | None
    grade_max: int | None
    source_kind: str
    source_note: str
    license_code: str
    license_note: str
    review_status: str
    publication_status: str
    is_test_fixture: bool
    local_demo_visible: bool = False
    content_notice: str | None
    chapter_revision_ids: list[uuid.UUID]
    knowledge_point_slugs: list[str]
    variants: list[ResourceVariantDTO]


class ResourceListDTO(BaseModel):
    items: list[ResourceSummaryDTO]
    profile: str


class AdminResourceListDTO(ResourceListDTO):
    total: int
    limit: int
    offset: int


class ResourceTicketDTO(BaseModel):
    """A short-lived, server-signed link. It is not a material identifier."""

    url: str
    expires_at: datetime
    variant: VariantLiteral
    notice: str


class ResourceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    kind: ResourceKindLiteral
    interactive_purpose: Literal["LESSON", "GAME", "EXPERIMENT"] | None = None
    interactive_subject: str | None = Field(default=None, max_length=80)
    stage: Literal["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"]
    grade_min: int | None = Field(default=None, ge=1, le=12)
    grade_max: int | None = Field(default=None, ge=1, le=12)
    source_kind: Literal["LEGACY_REUSED", "NEW_SOURCE", "SYNTHETIC_FIXTURE"]
    source_note: str = Field(default="", max_length=4000)
    license_code: Literal[
        "CC-BY", "CC-BY-SA", "CC0", "PROJECT-ORIGINAL", "SYNTHETIC-FIXTURE", "UNKNOWN"
    ]
    license_note: str = Field(default="", max_length=4000)
    chapter_revision_ids: list[uuid.UUID] = Field(default_factory=list, max_length=16)
    knowledge_point_slugs: list[str] = Field(default_factory=list, max_length=16)
    is_test_fixture: bool = False
    local_demo_visible: bool = False


class ResourcePatchRequest(BaseModel):
    """Only these fields may change; owner/reviewer/uploader are server-set."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    local_demo_visible: bool | None = None
    description: str | None = Field(default=None, max_length=4000)
    grade_min: int | None = Field(default=None, ge=1, le=12)
    grade_max: int | None = Field(default=None, ge=1, le=12)
    source_note: str | None = Field(default=None, max_length=4000)
    license_code: (
        Literal["CC-BY", "CC-BY-SA", "CC0", "PROJECT-ORIGINAL", "SYNTHETIC-FIXTURE", "UNKNOWN"]
        | None
    ) = None
    license_note: str | None = Field(default=None, max_length=4000)
    review_status: Literal["UNREVIEWED", "AUTO_VALIDATED", "HUMAN_APPROVED"] | None = None
    publication_status: Literal["DRAFT", "PUBLISHED", "WITHDRAWN"] | None = None
    chapter_revision_ids: list[uuid.UUID] | None = Field(default=None, max_length=16)


class ResourceUploadReceipt(BaseModel):
    resource_id: uuid.UUID
    variant: VariantLiteral
    filename: str
    mime: str
    size_bytes: int
    sha256: str


__all__ = [
    "AdminResourceListDTO",
    "ResourceCreateRequest",
    "ResourceListDTO",
    "ResourcePatchRequest",
    "ResourceSummaryDTO",
    "ResourceTicketDTO",
    "ResourceUploadReceipt",
    "ResourceVariantDTO",
]
