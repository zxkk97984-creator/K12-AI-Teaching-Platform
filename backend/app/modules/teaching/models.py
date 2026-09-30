"""Persistent conversation/run schema (T12).

Design rules baked into this schema:

* The user message, the run row and its lease are written in one **short**
  transaction. The gateway call happens after that commit, never inside it.
* Idempotency is a database constraint (``uq_teaching_runs_owner_key``), not an
  in-process map: two tabs, two processes or two workers cannot create two
  effective runs for the same (owner, idempotency key).
* Lease ownership is a token on the run row. A late worker whose token or
  deadline no longer matches cannot overwrite a newer state: it may only mark
  the run STALE while the run is still RUNNING.
* Validated assistant output is stored as an explicit card (message + sources +
  action), never as the raw gateway payload.
"""

from __future__ import annotations

import enum
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.identity.models import Base


class RunStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE = "STALE"


TERMINAL_RUN_STATUSES = (
    RunStatus.SUCCEEDED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
    RunStatus.STALE.value,
)


class MessageRole(enum.StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class LessonSession(Base):
    __tablename__ = "teaching_lesson_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapters.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    conversation_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LESSON", server_default="LESSON", index=True
    )
    title: Mapped[str | None] = mapped_column(String(200))
    creation_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    curriculum_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    teacher_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    grade: Mapped[int | None] = mapped_column(Integer)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="ORIENT")
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    phase_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    policy_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    fixture_allowance: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="session",
        order_by="ConversationMessage.created_at",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("base_revision >= 0", name="ck_teaching_sessions_base_revision"),
        CheckConstraint(
            "conversation_type IN ('LESSON', 'FREE')",
            name="ck_teaching_sessions_conversation_type",
        ),
        CheckConstraint(
            "(conversation_type = 'FREE' AND chapter_id IS NULL AND revision_id IS NULL) "
            "OR (conversation_type = 'LESSON' AND chapter_id IS NOT NULL "
            "AND revision_id IS NOT NULL)",
            name="ck_teaching_sessions_conversation_target",
        ),
        CheckConstraint(
            "stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_teaching_sessions_stage",
        ),
        CheckConstraint(
            "phase IN ('ORIENT', 'EXPLAIN', 'CHECK', 'PRACTICE', 'REFLECT', 'COMPLETED')",
            name="ck_teaching_sessions_phase",
        ),
        CheckConstraint(
            "lifecycle IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'STALE')",
            name="ck_teaching_sessions_lifecycle",
        ),
        CheckConstraint("phase_revision >= 0", name="ck_teaching_sessions_phase_revision"),
        UniqueConstraint("owner_user_id", "creation_key", name="uq_teaching_session_creation_key"),
    )


class ConversationMessage(Base):
    __tablename__ = "teaching_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teaching_lesson_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teaching_agent_runs.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    card: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    session: Mapped[LessonSession] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_teaching_messages_role"),
    )


class AgentRun(Base):
    __tablename__ = "teaching_agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teaching_lesson_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    event: Mapped[str] = mapped_column(String(24), nullable=False, default="ASK")
    scene_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    policy_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Revision of the owner-scoped personal memory visible when this turn was
    # created; changed memory makes a late result stale.
    memory_context_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RunStatus.QUEUED.value)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gateway_invocation_id: Mapped[str | None] = mapped_column(String(64))
    error_category: Mapped[str | None] = mapped_column(String(40))
    stale_reason: Mapped[str | None] = mapped_column(String(80))
    # A bounded provisional teaching reply for reconnectable SSE. It is never
    # copied into conversation history and is cleared on every terminal state.
    draft_markdown: Mapped[str | None] = mapped_column(Text)
    result_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teaching_messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_teaching_runs_owner_key"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE')",
            name="ck_teaching_runs_status",
        ),
        CheckConstraint("attempt >= 1", name="ck_teaching_runs_attempt"),
        CheckConstraint("memory_context_revision >= 0", name="ck_teaching_runs_memory_revision"),
    )


class RemoteBinding(Base):
    """Locally stored link to a remote (or fixture) execution identity."""

    __tablename__ = "teaching_remote_bindings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teaching_agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    remote_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    remote_id: Mapped[str] = mapped_column(String(300), nullable=False)
    remote_scope: Mapped[str | None] = mapped_column(String(400))
    remote_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("remote_kind IN ('FIXTURE', 'KNODO')", name="ck_teaching_bindings_kind"),
    )


class TeachingPhaseEvent(Base):
    """Append-only audit of local legal phase transitions."""

    __tablename__ = "teaching_phase_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teaching_lesson_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(24), nullable=False)
    from_phase: Mapped[str] = mapped_column(String(16), nullable=False)
    to_phase: Mapped[str] = mapped_column(String(16), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False)
    phase_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
