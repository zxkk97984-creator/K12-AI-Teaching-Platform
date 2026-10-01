"""Versioned curriculum content schema.

Authority (ADR-005): the local PostgreSQL database owns course, release, revision,
review and publication state. Files under ``curriculum/`` are the editable source
and the immutable snapshot mirror, never the authority for what a student may read.

Design notes
------------
* ``content_chapter_revisions`` rows are immutable: a database trigger rejects
  UPDATE and DELETE. Editing a chapter always creates a new revision.
* Review/publication state lives in ``content_chapter_review_states`` so the
  content body can stay immutable while review moves from UNREVIEWED to
  AUTO_VALIDATED to HUMAN_APPROVED and publication moves DRAFT -> PUBLISHED or
  WITHDRAWN.
* Only a real reviewer identity may produce HUMAN_APPROVED; the importer never
  sets it. A trigger stops a synthetic fixture from ever becoming PUBLISHED.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.identity.models import Base, Stage


class SourceKind(enum.StrEnum):
    LEGACY_REUSED = "LEGACY_REUSED"
    NEW_SOURCE = "NEW_SOURCE"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


class LicenseCode(enum.StrEnum):
    CC_BY = "CC-BY"
    CC_BY_SA = "CC-BY-SA"
    CC0 = "CC0"
    PROJECT_ORIGINAL = "PROJECT-ORIGINAL"
    SYNTHETIC_FIXTURE = "SYNTHETIC-FIXTURE"
    UNKNOWN = "UNKNOWN"


class ReviewStatus(enum.StrEnum):
    UNREVIEWED = "UNREVIEWED"
    AUTO_VALIDATED = "AUTO_VALIDATED"
    HUMAN_APPROVED = "HUMAN_APPROVED"


class PublicationStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"


class ContentProfile(enum.StrEnum):
    """Which content surface a runtime is allowed to serve.

    ``FORMAL`` is the production contract: only human approved, published,
    non-fixture revisions inside the student's stage/grade range.
    ``DEVELOPMENT`` additionally exposes synthetic fixtures and releases with
    explicit local_demo_visible permission. Withdrawn content stays hidden.
    """

    FORMAL = "formal"
    DEVELOPMENT = "development"


class Course(Base):
    __tablename__ = "content_courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stable_slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chapters: Mapped[list[Chapter]] = relationship(back_populates="course")

    __table_args__ = (
        CheckConstraint(
            "stable_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_content_courses_slug",
        ),
    )


class Chapter(Base):
    __tablename__ = "content_chapters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_courses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stable_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course: Mapped[Course] = relationship(back_populates="chapters")

    __table_args__ = (
        UniqueConstraint("course_id", "stable_slug", name="uq_content_chapters_course_slug"),
        CheckConstraint(
            "stable_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_content_chapters_slug"
        ),
        CheckConstraint("order_index >= 0", name="ck_content_chapters_order"),
    )


class Release(Base):
    __tablename__ = "content_releases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    is_test_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    local_demo_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('LEGACY_REUSED', 'NEW_SOURCE', 'SYNTHETIC_FIXTURE')",
            name="ck_content_releases_source_kind",
        ),
        CheckConstraint(
            "(source_kind = 'SYNTHETIC_FIXTURE') = is_test_fixture",
            name="ck_content_releases_fixture_kind",
        ),
        CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_content_releases_manifest_hash",
        ),
    )


class ChapterRevision(Base):
    __tablename__ = "content_chapter_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_releases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    grade_min: Mapped[int | None] = mapped_column(Integer)
    grade_max: Mapped[int | None] = mapped_column(Integer)
    objectives: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    body: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    license_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    release: Mapped[Release] = relationship()
    chapter: Mapped[Chapter] = relationship()
    review_state: Mapped[ChapterReviewState] = relationship(
        back_populates="revision", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("chapter_id", "revision", name="uq_content_revisions_chapter_revision"),
        CheckConstraint("revision >= 1", name="ck_content_revisions_number"),
        CheckConstraint(
            "stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_content_revisions_stage",
        ),
        CheckConstraint(
            "(grade_min IS NULL AND grade_max IS NULL) OR "
            "(grade_min IS NOT NULL AND grade_max IS NOT NULL AND grade_min <= grade_max "
            "AND grade_min >= CASE stage "
            "WHEN 'PRIMARY_LOWER' THEN 1 WHEN 'PRIMARY_UPPER' THEN 4 "
            "WHEN 'JUNIOR' THEN 7 ELSE 10 END "
            "AND grade_max <= CASE stage "
            "WHEN 'PRIMARY_LOWER' THEN 3 WHEN 'PRIMARY_UPPER' THEN 6 "
            "WHEN 'JUNIOR' THEN 9 ELSE 12 END)",
            name="ck_content_revisions_grade_range",
        ),
        CheckConstraint("jsonb_typeof(body) = 'array'", name="ck_content_revisions_body_array"),
        CheckConstraint(
            "jsonb_array_length(body) BETWEEN 1 AND 400",
            name="ck_content_revisions_body_length",
        ),
        CheckConstraint(
            "jsonb_typeof(objectives) = 'array'", name="ck_content_revisions_objectives_array"
        ),
        CheckConstraint(
            "jsonb_array_length(objectives) BETWEEN 1 AND 8",
            name="ck_content_revisions_objectives_length",
        ),
        CheckConstraint(
            "jsonb_typeof(source_manifest) = 'object'",
            name="ck_content_revisions_source_manifest_object",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name="ck_content_revisions_content_hash"
        ),
        CheckConstraint(
            "license_code IN ('CC-BY', 'CC-BY-SA', 'CC0', 'PROJECT-ORIGINAL', "
            "'SYNTHETIC-FIXTURE', 'UNKNOWN')",
            name="ck_content_revisions_license",
        ),
    )


class KnowledgePoint(Base):
    __tablename__ = "content_knowledge_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stable_slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "stable_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_content_knowledge_points_slug",
        ),
    )


class RevisionKnowledgePoint(Base):
    __tablename__ = "content_revision_knowledge_points"

    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_knowledge_points.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("revision_id", "position", name="uq_content_revision_kp_position"),
        CheckConstraint("position >= 0", name="ck_content_revision_kp_position"),
    )


class ChapterReviewState(Base):
    __tablename__ = "content_chapter_review_states"

    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNREVIEWED")
    reviewer: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)
    publication_status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    published_by: Mapped[str | None] = mapped_column(String(160))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by: Mapped[str | None] = mapped_column(String(160))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    revision: Mapped[ChapterRevision] = relationship(back_populates="review_state")

    __table_args__ = (
        CheckConstraint(
            "review_status IN ('UNREVIEWED', 'AUTO_VALIDATED', 'HUMAN_APPROVED')",
            name="ck_content_review_status",
        ),
        CheckConstraint(
            "publication_status IN ('DRAFT', 'PUBLISHED', 'WITHDRAWN')",
            name="ck_content_publication_status",
        ),
        CheckConstraint(
            "(review_status = 'HUMAN_APPROVED') = "
            "(reviewer IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_content_review_human_evidence",
        ),
        CheckConstraint(
            "review_status <> 'AUTO_VALIDATED' OR (reviewer IS NULL AND reviewed_at IS NULL)",
            name="ck_content_review_auto_has_no_reviewer",
        ),
        CheckConstraint(
            "publication_status <> 'PUBLISHED' OR "
            "(review_status = 'HUMAN_APPROVED' AND published_by IS NOT NULL "
            "AND published_at IS NOT NULL)",
            name="ck_content_published_requires_approval",
        ),
        CheckConstraint(
            "(publication_status = 'WITHDRAWN') = "
            "(withdrawn_by IS NOT NULL AND withdrawn_at IS NOT NULL)",
            name="ck_content_withdrawn_evidence",
        ),
    )


class ReadingEventKind(enum.StrEnum):
    """Behaviour only. There is no mastery/completion value in this enum."""

    ENTER = "ENTER"
    SECTION_VIEW = "SECTION_VIEW"
    BLOCK_VIEW = "BLOCK_VIEW"
    SELECT_TEXT = "SELECT_TEXT"
    RESUME = "RESUME"
    LEAVE = "LEAVE"


class ReadingEvent(Base):
    """Minimal, owner-scoped reading behaviour record.

    Deliberately stores only identifiers and the *length* of a selected text
    (never the text itself, never a percentage score). Deleting the owning user
    cascades; chapter/revision references stay RESTRICT so history never
    silently points at removed curriculum.
    """

    __tablename__ = "content_reading_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    client_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    section_key: Mapped[str | None] = mapped_column(String(80))
    block_id: Mapped[str | None] = mapped_column(String(16))
    selected_text_length: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "client_event_id", name="uq_content_reading_user_client"),
        CheckConstraint(
            "event_kind IN ('ENTER', 'SECTION_VIEW', 'BLOCK_VIEW', "
            "'SELECT_TEXT', 'RESUME', 'LEAVE')",
            name="ck_content_reading_event_kind",
        ),
        CheckConstraint(
            "client_event_id ~ '^[A-Za-z0-9._:-]{8,64}$'",
            name="ck_content_reading_client_event_id",
        ),
        CheckConstraint(
            "selected_text_length IS NULL OR "
            "(selected_text_length >= 0 AND selected_text_length <= 500)",
            name="ck_content_reading_selected_length",
        ),
        CheckConstraint(
            "(event_kind <> 'SELECT_TEXT') OR selected_text_length IS NOT NULL",
            name="ck_content_reading_select_requires_length",
        ),
        CheckConstraint(
            "(event_kind = 'SELECT_TEXT') OR selected_text_length IS NULL",
            name="ck_content_reading_length_only_for_select",
        ),
    )


__all__ = [
    "Base",
    "Chapter",
    "ChapterReviewState",
    "ChapterRevision",
    "ContentProfile",
    "Course",
    "KnowledgePoint",
    "LicenseCode",
    "PublicationStatus",
    "Release",
    "ReviewStatus",
    "ReadingEvent",
    "ReadingEventKind",
    "RevisionKnowledgePoint",
    "SourceKind",
    "Stage",
]
