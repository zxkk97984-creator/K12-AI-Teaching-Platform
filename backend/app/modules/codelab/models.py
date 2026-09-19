from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.identity.models import Base


class CodeTaskRevision(Base):
    """Immutable imported task metadata; trusted oracle code is not stored here."""

    __tablename__ = "codelab_task_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", index=True)
    is_test_fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNREVIEWED")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    starter_code: Mapped[str] = mapped_column(Text, nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(64), nullable=False)
    io_contract: Mapped[dict] = mapped_column(JSONB, nullable=False)
    examples: Mapped[list] = mapped_column(JSONB, nullable=False)
    test_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rubric: Mapped[dict] = mapped_column(JSONB, nullable=False)
    chapter_binding: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source: Mapped[dict] = mapped_column(JSONB, nullable=False)
    definition_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("task_id", "revision", name="uq_codelab_task_revision"),
        CheckConstraint("revision >= 1", name="ck_codelab_task_revision_positive"),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_codelab_task_status"
        ),
        CheckConstraint(
            "review_status IN ('UNREVIEWED', 'HUMAN_REVIEWED')",
            name="ck_codelab_task_review_status",
        ),
        CheckConstraint(
            "jsonb_typeof(io_contract) = 'object'", name="ck_codelab_task_io_contract_object"
        ),
        CheckConstraint("jsonb_typeof(examples) = 'array'", name="ck_codelab_task_examples_array"),
        CheckConstraint(
            "jsonb_typeof(test_manifest) = 'object'",
            name="ck_codelab_task_manifest_object",
        ),
        CheckConstraint(
            "jsonb_typeof(chapter_binding) = 'object'",
            name="ck_codelab_task_binding_object",
        ),
        CheckConstraint(
            "definition_sha256 ~ '^[0-9a-f]{64}$'", name="ck_codelab_task_definition_sha256"
        ),
    )


class CodeDraft(Base):
    """Owner-scoped code draft for one immutable task revision."""

    __tablename__ = "codelab_code_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "task_id", "task_revision", name="uq_codelab_draft_owner_task"
        ),
        CheckConstraint("task_revision >= 1", name="ck_codelab_draft_revision_positive"),
        CheckConstraint("code_sha256 ~ '^[0-9a-f]{64}$'", name="ck_codelab_draft_code_sha256"),
    )


class CodeRun(Base):
    """A durable owner-scoped run snapshot and trusted result projection."""

    __tablename__ = "codelab_code_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    lesson_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    code_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", index=True)
    execution_status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED")
    correctness_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="NOT_VERIFIED"
    )
    deterministic_score: Mapped[float | None] = mapped_column(Float)
    result: Mapped[dict | None] = mapped_column(JSONB)
    feedback_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNAVAILABLE")
    feedback: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "idempotency_key", name="uq_codelab_run_owner_idempotency"
        ),
        CheckConstraint("task_revision >= 1", name="ck_codelab_run_revision_positive"),
        CheckConstraint("code_sha256 ~ '^[0-9a-f]{64}$'", name="ck_codelab_run_code_sha256"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT', "
            "'OUTPUT_LIMIT', 'UNAVAILABLE', 'SYSTEM_ERROR', 'CANCELLED')",
            name="ck_codelab_run_status",
        ),
        CheckConstraint(
            "execution_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT', "
            "'OUTPUT_LIMIT', 'UNAVAILABLE', 'SYSTEM_ERROR', 'CANCELLED')",
            name="ck_codelab_run_execution_status",
        ),
        CheckConstraint(
            "correctness_status IN ('PASSED', 'PARTIAL', 'FAILED', 'NOT_VERIFIED')",
            name="ck_codelab_run_correctness_status",
        ),
        CheckConstraint(
            "feedback_status IN ('UNAVAILABLE', 'READY', 'FAILED', 'STALE')",
            name="ck_codelab_run_feedback_status",
        ),
    )
