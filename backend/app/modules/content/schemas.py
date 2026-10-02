"""Strict schemas for the curriculum source packages and read models.

A package is data. Nothing inside a package is executed, imported or treated as
an instruction. Unknown keys, unknown block types, absolute or traversal paths
and unlisted licenses are rejected instead of being silently dropped.
"""

from __future__ import annotations

import enum
import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.content.models import (
    ContentProfile,
    LicenseCode,
    PublicationStatus,
    ReadingEventKind,
    ReviewStatus,
    SourceKind,
    Stage,
)

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
COMMIT_PATTERN = r"^[0-9a-f]{7,40}$"
ASSET_PATTERN = r"^assets/[A-Za-z0-9._-]+$"

RELEASE_SCHEMA_VERSION = "k12.content.release.v1"
COURSE_SCHEMA_VERSION = "k12.content.course.v1"
CHAPTER_CONTENT_SCHEMA_VERSION = "k12.content.chapter-blocks.v1"

STAGE_GRADE_BOUNDS: dict[str, tuple[int, int]] = {
    Stage.PRIMARY_LOWER.value: (1, 3),
    Stage.PRIMARY_UPPER.value: (4, 6),
    Stage.JUNIOR.value: (7, 9),
    Stage.SENIOR.value: (10, 12),
}

# Only these licenses may reach the database. UNKNOWN is accepted as a label but
# may never be published; unknown strings (typos, invented licenses) fail closed.
ALLOWED_LICENSE_CODES: frozenset[str] = frozenset(code.value for code in LicenseCode)

Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, min_length=2, max_length=120)]
Sha256 = Annotated[str, StringConstraints(pattern=SHA256_PATTERN, min_length=64, max_length=64)]
Commit = Annotated[str, StringConstraints(pattern=COMMIT_PATTERN, min_length=7, max_length=40)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
BodyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
FilePath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]

TRAVERSAL_RE = re.compile(r"(^/)|(^[A-Za-z]:)|(\.\.)")


def is_safe_relative_path(value: str) -> bool:
    """Reject absolute paths, drive letters and any traversal segment."""

    if not value or TRAVERSAL_RE.search(value):
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockType(enum.StrEnum):
    TITLE = "TITLE"
    SECTION = "SECTION"
    PARAGRAPH = "PARAGRAPH"
    KNOWLEDGE_CARD = "KNOWLEDGE_CARD"
    CALLOUT = "CALLOUT"
    FIGURE = "FIGURE"
    MARKDOWN = "MARKDOWN"


class ExampleSpec(StrictModel):
    label: ShortText
    text: BodyText


class BlockSpec(StrictModel):
    """One rendered teaching block; the same shape is stored and returned."""

    type: BlockType
    text: BodyText | None = None
    title: ShortText | None = None
    key: (
        Annotated[str, StringConstraints(pattern=SLUG_PATTERN, min_length=2, max_length=80)] | None
    ) = None
    mark: ShortText | None = None
    caption: ShortText | None = None
    alt: ShortText | None = None
    src: Annotated[str, StringConstraints(pattern=ASSET_PATTERN, max_length=200)] | None = None
    example: ExampleSpec | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> BlockSpec:
        used = {
            name
            for name in ("text", "title", "key", "mark", "caption", "alt", "src", "example")
            if getattr(self, name) is not None
        }
        allowed: dict[BlockType, set[str]] = {
            BlockType.TITLE: {"text"},
            BlockType.SECTION: {"key", "text"},
            BlockType.PARAGRAPH: {"text", "mark"},
            BlockType.KNOWLEDGE_CARD: {"title", "text", "example"},
            BlockType.CALLOUT: {"title", "text"},
            BlockType.FIGURE: {"alt", "caption", "src"},
            BlockType.MARKDOWN: {"text"},
        }
        extra = used - allowed[self.type]
        if extra:
            raise ValueError(f"{self.type} block does not allow fields: {sorted(extra)}")
        required: dict[BlockType, set[str]] = {
            BlockType.TITLE: {"text"},
            BlockType.SECTION: {"key"},
            BlockType.PARAGRAPH: {"text"},
            BlockType.KNOWLEDGE_CARD: {"title", "text"},
            BlockType.CALLOUT: {"title", "text"},
            BlockType.FIGURE: {"alt", "caption"},
            BlockType.MARKDOWN: {"text"},
        }
        missing = required[self.type] - used
        if missing:
            raise ValueError(f"{self.type} block requires fields: {sorted(missing)}")
        if self.mark is not None and self.text is not None and self.mark not in self.text:
            raise ValueError("mark must be a substring of the block text")
        return self


class KnowledgePointSpec(StrictModel):
    slug: Slug
    name: ShortText
    topic: ShortText
    description: BodyText


class ChapterSourceSpec(StrictModel):
    source_commit: Commit | None = None
    source_path: FilePath
    original_sha256: Sha256
    conversion: ShortText

    @model_validator(mode="after")
    def validate_path(self) -> ChapterSourceSpec:
        if not is_safe_relative_path(self.source_path):
            raise ValueError("source_path must be a relative path without traversal")
        return self


class ChapterSpec(StrictModel):
    stable_slug: Slug
    revision: int = Field(ge=1, le=10_000)
    order_index: int = Field(ge=0, le=1000)
    title: ShortText
    stage: Stage
    grade_min: int | None = Field(default=None, ge=1, le=12)
    grade_max: int | None = Field(default=None, ge=1, le=12)
    objectives: list[ShortText] = Field(min_length=1, max_length=8)
    knowledge_points: list[Slug] = Field(min_length=1, max_length=32)
    license_code: LicenseCode
    license_notes: ShortText | None = None
    source: ChapterSourceSpec
    content_file: FilePath
    example_count: int = Field(default=0, ge=0, le=50)

    @model_validator(mode="after")
    def validate_ranges_and_paths(self) -> ChapterSpec:
        low, high = STAGE_GRADE_BOUNDS[self.stage.value]
        if (self.grade_min is None) != (self.grade_max is None):
            raise ValueError("grade_min and grade_max must both be set or both be null")
        if self.grade_min is not None and self.grade_max is not None:
            if self.grade_min > self.grade_max:
                raise ValueError("grade_min must not exceed grade_max")
            if self.grade_min < low or self.grade_max > high:
                raise ValueError(
                    f"grade range must stay inside stage {self.stage.value} {low}-{high}"
                )
        if not is_safe_relative_path(self.content_file):
            raise ValueError("content_file must be a relative path without traversal")
        if len(set(self.knowledge_points)) != len(self.knowledge_points):
            raise ValueError("knowledge_points must not repeat a slug")
        return self


class TextbookInfo(StrictModel):
    """Student-safe book metadata. Reference answers never belong here."""

    book_id: Slug
    stage_group: Literal["PRIMARY", "JUNIOR", "SENIOR"]
    language: Literal["zh-CN"]
    ai_assisted: Literal[True]
    review_status: Literal["UNREVIEWED"]
    chapter_count: int = Field(ge=1, le=64)
    body_han_chars: int = Field(ge=1)
    prerequisites: list[ShortText] = Field(min_length=1, max_length=12)
    learning_outcomes: list[ShortText] = Field(min_length=1, max_length=12)
    preface: Annotated[str, StringConstraints(min_length=100, max_length=12000)]


class CourseSpec(StrictModel):
    schema_version: str
    stable_slug: Slug
    title: ShortText
    topic: ShortText
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)
    ]
    knowledge_points: list[KnowledgePointSpec] = Field(min_length=1, max_length=64)
    chapters: list[ChapterSpec] = Field(min_length=1, max_length=64)
    textbook: TextbookInfo | None = None

    @model_validator(mode="after")
    def validate_course(self) -> CourseSpec:
        if self.schema_version != COURSE_SCHEMA_VERSION:
            raise ValueError(f"unsupported course schema_version: {self.schema_version}")
        kp_slugs = [item.slug for item in self.knowledge_points]
        if len(set(kp_slugs)) != len(kp_slugs):
            raise ValueError("knowledge_points must be unique inside a course")
        chapter_slugs = [item.stable_slug for item in self.chapters]
        if len(set(chapter_slugs)) != len(chapter_slugs):
            raise ValueError("chapters must be unique inside a course")
        known = set(kp_slugs)
        for chapter in self.chapters:
            unknown = set(chapter.knowledge_points) - known
            if unknown:
                raise ValueError(
                    f"chapter {chapter.stable_slug} references undeclared knowledge points: "
                    f"{sorted(unknown)}"
                )
        return self


class ReleaseSpec(StrictModel):
    schema_version: str
    release_key: Slug
    source_kind: SourceKind
    is_test_fixture: bool
    local_demo_visible: bool = False
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=5, max_length=2000)
    ]
    license_code: LicenseCode
    license_notes: ShortText | None = None
    course_files: list[FilePath] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_release(self) -> ReleaseSpec:
        if self.schema_version != RELEASE_SCHEMA_VERSION:
            raise ValueError(f"unsupported release schema_version: {self.schema_version}")
        fixture = self.source_kind == SourceKind.SYNTHETIC_FIXTURE
        if fixture != self.is_test_fixture:
            raise ValueError("is_test_fixture must be true exactly for SYNTHETIC_FIXTURE releases")
        for item in self.course_files:
            if not is_safe_relative_path(item):
                raise ValueError("course_files entries must be relative paths without traversal")
        if len(set(self.course_files)) != len(self.course_files):
            raise ValueError("course_files must be unique")
        return self


class KnowledgePointDTO(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    slug: Slug
    name: str
    topic: str
    description: str


class ChapterSummaryDTO(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    chapter_id: uuid.UUID
    course_id: uuid.UUID
    course_slug: str
    course_title: str
    chapter_slug: str
    title: str
    order_index: int
    stage: Stage
    grade_min: int | None
    grade_max: int | None
    revision: int
    revision_id: uuid.UUID
    source_kind: SourceKind
    publication_status: PublicationStatus
    review_status: ReviewStatus
    is_test_fixture: bool
    content_notice: str | None


class CourseSummaryDTO(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    course_id: uuid.UUID
    slug: str
    title: str
    topic: str
    description: str
    chapters: list[ChapterSummaryDTO]
    textbook: TextbookInfo | None = None


class RenderedBlock(BlockSpec):
    """A validated content block plus the stable per-revision block id.

    Block ids are positional (``b1``..``bN``) inside an immutable revision, so
    a client can reference a block without inventing or rewriting content.
    """

    block_id: Annotated[str, StringConstraints(pattern=r"^b[0-9]{1,4}$", max_length=8)]


class UnknownBlockDTO(StrictModel):
    """Controlled placeholder for a stored block that no longer validates.

    The raw payload is intentionally not echoed: the reader shows the position
    and a reason instead of rendering unreviewed content.
    """

    block_id: Annotated[str, StringConstraints(pattern=r"^b[0-9]{1,4}$", max_length=8)]
    type: Literal["UNSUPPORTED"] = "UNSUPPORTED"
    reason: str


class NeighborRefDTO(StrictModel):
    chapter_id: uuid.UUID
    slug: str
    title: str
    revision: int


class ChapterNavigationDTO(StrictModel):
    prev: NeighborRefDTO | None
    next: NeighborRefDTO | None


class SourceRefDTO(StrictModel):
    """Whitelisted provenance for the reader.

    The raw stored manifest is deliberately not returned: students only need
    where the text came from and under which license, not internal review keys,
    content hashes or archive identifiers.
    """

    source_kind: SourceKind | None
    source_commit: str | None
    source_path: str | None
    conversion: str | None
    license_code: LicenseCode


class ChapterDetailDTO(ChapterSummaryDTO):
    objectives: list[str]
    knowledge_points: list[KnowledgePointDTO]
    blocks: list[RenderedBlock | UnknownBlockDTO]
    source: SourceRefDTO
    license_code: LicenseCode
    navigation: ChapterNavigationDTO


class CourseListDTO(StrictModel):
    items: list[CourseSummaryDTO]


class ReadingEventRequest(StrictModel):
    client_event_id: Annotated[
        str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{8,64}$", min_length=8, max_length=64)
    ]
    chapter_id: uuid.UUID
    revision: int = Field(ge=1, le=10_000)
    event_kind: ReadingEventKind
    section_key: Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=80)] | None = (
        None
    )
    block_id: Annotated[str, StringConstraints(pattern=r"^b[0-9]{1,4}$", max_length=8)] | None = (
        None
    )
    selected_text_length: int | None = Field(default=None, ge=0, le=500)

    @model_validator(mode="after")
    def validate_kind_payload(self) -> ReadingEventRequest:
        is_select = self.event_kind is ReadingEventKind.SELECT_TEXT
        if is_select and self.selected_text_length is None:
            raise ValueError("SELECT_TEXT requires selected_text_length")
        if not is_select and self.selected_text_length is not None:
            raise ValueError("selected_text_length is only allowed for SELECT_TEXT")
        return self


class ReadingEventReceipt(StrictModel):
    event_id: uuid.UUID
    duplicate: bool
    recorded_at: datetime


class ReadingStateDTO(StrictModel):
    chapter_id: uuid.UUID
    revision: int
    revision_id: uuid.UUID
    event_kind: ReadingEventKind
    section_key: str | None
    block_id: str | None
    created_at: datetime
    is_current_revision: bool


class PageContextRequest(StrictModel):
    chapter_id: uuid.UUID
    revision: int = Field(ge=1, le=10_000)
    section_key: Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=80)] | None = (
        None
    )
    block_id: Annotated[str, StringConstraints(pattern=r"^b[0-9]{1,4}$", max_length=8)] | None = (
        None
    )
    selected_text: str | None = Field(default=None, max_length=500)


class PageContextDTO(StrictModel):
    """Server-validated page context. Identifiers + limited selection only."""

    chapter_id: uuid.UUID
    revision: int
    source_id: str
    section_key: str | None
    block_id: str | None
    selected_text: str | None
    selected_text_chars: int
    generated_at: datetime


class ViewerScope(StrictModel):
    """Server-side viewer facts; never built from client supplied roles."""

    stage: Stage | None
    grade: int | None = Field(default=None, ge=1, le=12)
    profile: ContentProfile = ContentProfile.FORMAL

    @model_validator(mode="after")
    def validate_scope(self) -> ViewerScope:
        if self.grade is not None and self.stage is None:
            raise ValueError("grade requires a stage")  # mirrors T05 profile rule
        if self.grade is not None and self.stage is not None:
            low, high = STAGE_GRADE_BOUNDS[self.stage.value]
            if not low <= self.grade <= high:
                raise ValueError("grade must match the stage")
        return self
