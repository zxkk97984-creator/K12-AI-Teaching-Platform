"""Resource metadata, variants and curriculum bindings (T20).

Authority rules:

* Metadata (stage, licence, review, publication, storage key) lives in
  PostgreSQL; the bytes live under the configured storage root.
* Source file and preview file are separate ``resource_variants`` rows. The
  short-lived download ticket is **never** a row: it is a signed, expiring
  value derived on demand (see ``app.core.storage.tickets``).
* ``resource_items`` reuses the content module's review/publication vocabulary
  so a resource cannot claim a state the curriculum cannot.
* A database trigger stops synthetic fixtures from ever becoming PUBLISHED.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.content.models import (  # read-only reuse of the frozen vocabulary
    LicenseCode,
    PublicationStatus,
    ReviewStatus,
    SourceKind,
)
from app.modules.identity.models import Base


class ResourceKind(enum.StrEnum):
    WORD = "WORD"
    SLIDES = "SLIDES"
    VIDEO = "VIDEO"
    PDF = "PDF"
    IMAGE = "IMAGE"


class ResourceVariantKind(enum.StrEnum):
    """Source file vs. derived preview. The temporary link is neither."""

    SOURCE = "SOURCE"
    PREVIEW = "PREVIEW"


_KIND_SQL = "('WORD', 'SLIDES', 'VIDEO', 'PDF', 'IMAGE')"
_VARIANT_SQL = "('SOURCE', 'PREVIEW')"
_SOURCE_SQL = "('LEGACY_REUSED', 'NEW_SOURCE', 'SYNTHETIC_FIXTURE')"
_LICENSE_SQL = "('CC-BY', 'CC-BY-SA', 'CC0', 'PROJECT-ORIGINAL', 'SYNTHETIC-FIXTURE', 'UNKNOWN')"
_REVIEW_SQL = "('UNREVIEWED', 'AUTO_VALIDATED', 'HUMAN_APPROVED')"
_PUBLICATION_SQL = "('DRAFT', 'PUBLISHED', 'WITHDRAWN')"
_STAGE_SQL = "('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')"


class Resource(Base):
    __tablename__ = "resource_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stable_slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    grade_min: Mapped[int | None] = mapped_column(Integer)
    grade_max: Mapped[int | None] = mapped_column(Integer)
    # provenance / authorization
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    license_code: Mapped[str] = mapped_column(String(32), nullable=False)
    license_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # review / publication
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNREVIEWED")
    publication_status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_test_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    variants: Mapped[list[ResourceVariant]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )
    chapter_links: Mapped[list[ResourceChapterLink]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )
    knowledge_links: Mapped[list[ResourceKnowledgePoint]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(f"kind IN {_KIND_SQL}", name="ck_resource_items_kind"),
        CheckConstraint(f"stage IN {_STAGE_SQL}", name="ck_resource_items_stage"),
        CheckConstraint(
            "(grade_min IS NULL AND grade_max IS NULL) OR "
            "(grade_min IS NOT NULL AND grade_max IS NOT NULL AND grade_min <= grade_max "
            "AND grade_min >= CASE stage "
            "WHEN 'PRIMARY_LOWER' THEN 1 WHEN 'PRIMARY_UPPER' THEN 4 "
            "WHEN 'JUNIOR' THEN 7 ELSE 10 END "
            "AND grade_max <= CASE stage "
            "WHEN 'PRIMARY_LOWER' THEN 3 WHEN 'PRIMARY_UPPER' THEN 6 "
            "WHEN 'JUNIOR' THEN 9 ELSE 12 END)",
            name="ck_resource_items_grade_range",
        ),
        CheckConstraint(f"source_kind IN {_SOURCE_SQL}", name="ck_resource_items_source_kind"),
        CheckConstraint(f"license_code IN {_LICENSE_SQL}", name="ck_resource_items_license"),
        CheckConstraint(f"review_status IN {_REVIEW_SQL}", name="ck_resource_items_review_status"),
        CheckConstraint(
            f"publication_status IN {_PUBLICATION_SQL}",
            name="ck_resource_items_publication_status",
        ),
        CheckConstraint(
            "(source_kind = 'SYNTHETIC_FIXTURE') = is_test_fixture",
            name="ck_resource_items_fixture_kind",
        ),
        CheckConstraint(
            "(review_status <> 'HUMAN_APPROVED') OR "
            "(reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_resource_items_human_review_actor",
        ),
        CheckConstraint("stable_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_resource_items_slug"),
    )


class ResourceVariant(Base):
    """One stored file. ``SOURCE`` is the original, ``PREVIEW`` is derived."""

    __tablename__ = "resource_variants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_mime: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    detected_mime: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    resource: Mapped[Resource] = relationship(back_populates="variants")

    __table_args__ = (
        UniqueConstraint("resource_id", "variant", name="uq_resource_variants_resource_variant"),
        CheckConstraint(f"variant IN {_VARIANT_SQL}", name="ck_resource_variants_variant"),
        CheckConstraint("size_bytes > 0", name="ck_resource_variants_size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_resource_variants_sha256"),
        CheckConstraint("storage_key !~ '\\.\\.'", name="ck_resource_variants_no_traversal"),
        CheckConstraint("storage_key !~ '^/'", name="ck_resource_variants_relative"),
        CheckConstraint("storage_key !~ '\\\\'", name="ck_resource_variants_no_backslash"),
    )


class ResourceChapterLink(Base):
    """Binds a resource to one immutable chapter revision (the T06 unit)."""

    __tablename__ = "resource_chapter_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    resource: Mapped[Resource] = relationship(back_populates="chapter_links")

    __table_args__ = (
        UniqueConstraint(
            "resource_id", "chapter_revision_id", name="uq_resource_chapter_links_pair"
        ),
    )


class ResourceKnowledgePoint(Base):
    __tablename__ = "resource_knowledge_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_knowledge_points.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    resource: Mapped[Resource] = relationship(back_populates="knowledge_links")

    __table_args__ = (
        UniqueConstraint(
            "resource_id", "knowledge_point_id", name="uq_resource_knowledge_points_pair"
        ),
    )


__all__ = [
    "LicenseCode",
    "PublicationStatus",
    "Resource",
    "ResourceChapterLink",
    "ResourceKind",
    "ResourceKnowledgePoint",
    "ResourceVariant",
    "ResourceVariantKind",
    "ReviewStatus",
    "SourceKind",
]
