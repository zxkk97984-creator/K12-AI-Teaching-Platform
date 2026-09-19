from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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
