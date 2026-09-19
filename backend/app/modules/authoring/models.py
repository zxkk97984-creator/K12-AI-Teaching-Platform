"""Authoring models (T22): durable jobs, real artefacts, human reviews, publications.

Invariants that must hold even if service code is wrong:

* ``authoring_artifacts`` rows describe files that really exist on disk. An
  ``asset_request`` (a request for artwork/video) is **not** an artefact and
  never creates a row here.
* ``authoring_packages.status`` may only become ``HUMAN_APPROVED`` when a real
  human review row exists **and** at least one verified artefact exists. This is
  enforced by a database trigger, so no AI path can self-approve.
* A publication requires an HUMAN_APPROVED package with verified artefacts and
  is idempotent through ``idempotency_key``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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

from app.modules.identity.models import Base


class JobStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PackageStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    AUTO_VALIDATED = "AUTO_VALIDATED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"


class ArtifactKind(enum.StrEnum):
    LESSON_MARKDOWN = "LESSON_MARKDOWN"
    PACKAGE_MANIFEST = "PACKAGE_MANIFEST"


class ActorKind(enum.StrEnum):
    HUMAN_ADMIN = "HUMAN_ADMIN"


class ReviewDecision(enum.StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


_JOB_SQL = "('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')"
_PACKAGE_SQL = "('DRAFT', 'AUTO_VALIDATED', 'HUMAN_APPROVED', 'PUBLISHED', 'CANCELLED')"
_ARTIFACT_SQL = "('LESSON_MARKDOWN', 'PACKAGE_MANIFEST')"
_ACTOR_SQL = "('HUMAN_ADMIN')"
_DECISION_SQL = "('APPROVED', 'REJECTED')"


class AuthoringJob(Base):
    """One Designer LESSON_PACKAGE_DRAFT call. The row is the source of truth."""

    __tablename__ = "authoring_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    chapter_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(
        String(48), nullable=False, default="LESSON_PACKAGE_DRAFT"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    gateway_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    run_ref: Mapped[str | None] = mapped_column(String(120))
    error_code: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    packages: Mapped[list[AuthoringPackage]] = relationship(back_populates="job")

    __table_args__ = (
        CheckConstraint(f"status IN {_JOB_SQL}", name="ck_authoring_jobs_status"),
        CheckConstraint(
            "attempt >= 0 AND max_attempts >= 1 AND attempt <= max_attempts",
            name="ck_authoring_jobs_budget",
        ),
    )


class AuthoringPackage(Base):
    """The reviewed unit. Its spec is structured data; answers stay out of it."""

    __tablename__ = "authoring_packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authoring_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # asset requests are recorded for transparency but never counted as output
    asset_requests: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[AuthoringJob] = relationship(back_populates="packages")
    artifacts: Mapped[list[AuthoringArtifact]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[AuthoringReview]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(f"status IN {_PACKAGE_SQL}", name="ck_authoring_packages_status"),
        CheckConstraint("revision >= 1", name="ck_authoring_packages_revision"),
        CheckConstraint(
            "jsonb_typeof(asset_requests) = 'array'",
            name="ck_authoring_packages_asset_requests_array",
        ),
    )


class AuthoringArtifact(Base):
    """A real file on disk (deterministic local renderer or verified download)."""

    __tablename__ = "authoring_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authoring_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_mime: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rendered_by: Mapped[str] = mapped_column(String(32), nullable=False, default="LOCAL_RENDERER")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    package: Mapped[AuthoringPackage] = relationship(back_populates="artifacts")

    __table_args__ = (
        CheckConstraint(f"kind IN {_ARTIFACT_SQL}", name="ck_authoring_artifacts_kind"),
        CheckConstraint("size_bytes > 0", name="ck_authoring_artifacts_size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_authoring_artifacts_sha256"),
        CheckConstraint(
            "storage_key !~ '\\.\\.' AND storage_key !~ '^/'",
            name="ck_authoring_artifacts_key_safe",
        ),
        UniqueConstraint("package_id", "kind", name="uq_authoring_artifacts_package_kind"),
    )


class AuthoringReview(Base):
    """A real human review. Only an admin session can create one."""

    __tablename__ = "authoring_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authoring_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="HUMAN_ADMIN")
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    package_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    package: Mapped[AuthoringPackage] = relationship(back_populates="reviews")

    __table_args__ = (
        CheckConstraint(f"actor_kind IN {_ACTOR_SQL}", name="ck_authoring_reviews_actor_kind"),
        CheckConstraint(f"decision IN {_DECISION_SQL}", name="ck_authoring_reviews_decision"),
    )


class AuthoringPublication(Base):
    """An immutable published revision of a package."""

    __tablename__ = "authoring_publications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authoring_packages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    published_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bundle_ref: Mapped[str] = mapped_column(String(400), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_authoring_publications_revision"),
        CheckConstraint(
            "artifact_sha256 ~ '^[0-9a-f]{64}$'", name="ck_authoring_publications_sha256"
        ),
        UniqueConstraint(
            "package_id", "revision", name="uq_authoring_publications_package_revision"
        ),
    )


__all__ = [
    "ActorKind",
    "ArtifactKind",
    "AuthoringArtifact",
    "AuthoringJob",
    "AuthoringPackage",
    "AuthoringPublication",
    "AuthoringReview",
    "JobStatus",
    "PackageStatus",
    "ReviewDecision",
]
