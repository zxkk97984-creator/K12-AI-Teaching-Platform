"""Student-owned, revocable memory (T18 K2/K5/K10).

A memory is *never* written by a model here: candidates are derived locally by
explicit rules, and only the student can confirm/dispute/edit/forget them. Every
transition appends a ``memory_events`` row, so an edit keeps the previous
statement and a forgotten candidate is terminal.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.identity.models import Base

MEMORY_STATUSES = ("CANDIDATE", "ACTIVE", "DISPUTED", "REMOVED")
MEMORY_ACTIONS = ("CREATE", "CONFIRM", "DISPUTE", "EDIT", "FORGET")
MEMORY_KINDS = ("STUDY_STRATEGY", "PREFERENCE")
DERIVATION_RULE_VERSION = "k12.memory.rule.v1"


class MemoryCandidate(Base):
    __tablename__ = "memory_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CANDIDATE")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    basis_evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    basis_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    derivation_key: Mapped[str] = mapped_column(String(96), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="RULE_DERIVED")
    derivation_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("owner_user_id", "derivation_key", name="uq_memory_candidates_derivation"),
        CheckConstraint(
            "status IN ('CANDIDATE', 'ACTIVE', 'DISPUTED', 'REMOVED')",
            name="ck_memory_candidates_status",
        ),
        CheckConstraint(
            "kind IN ('STUDY_STRATEGY', 'PREFERENCE')", name="ck_memory_candidates_kind"
        ),
        CheckConstraint("origin = 'RULE_DERIVED'", name="ck_memory_candidates_origin"),
        CheckConstraint("revision >= 1", name="ck_memory_candidates_revision"),
        CheckConstraint(
            "jsonb_typeof(basis_evidence_ids) = 'array'",
            name="ck_memory_candidates_basis_array",
        ),
        CheckConstraint(
            "jsonb_typeof(content) = 'object'", name="ck_memory_candidates_content_object"
        ),
    )


class MemoryEvent(Base):
    """Append-only history: an edit keeps the previous statement."""

    __tablename__ = "memory_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    from_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    to_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_before: Mapped[str | None] = mapped_column(Text)
    statement_after: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(16), nullable=False, default="STUDENT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('CREATE', 'CONFIRM', 'DISPUTE', 'EDIT', 'FORGET')",
            name="ck_memory_events_action",
        ),
        CheckConstraint("actor = 'STUDENT'", name="ck_memory_events_actor"),
    )
