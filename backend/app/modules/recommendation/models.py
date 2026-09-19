"""Event-driven recommendation snapshots and student feedback (T19)."""

from __future__ import annotations

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
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.identity.models import Base

FEEDBACK_STATES = ("IGNORED", "ACTIVE")


class RecommendationSnapshot(Base):
    """One stored next-step decision; a changed input set supersedes it."""

    __tablename__ = "recommendation_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    thresholds_version: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    alternatives: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    basis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    effect_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "source_revision", name="uq_recommendation_snapshots_revision"
        ),
        UniqueConstraint("owner_user_id", "inputs_hash", name="uq_recommendation_snapshots_inputs"),
        CheckConstraint("source_revision >= 1", name="ck_recommendation_snapshots_revision"),
        CheckConstraint(
            "jsonb_typeof(primary_item) = 'object'", name="ck_recommendation_snapshots_primary"
        ),
        CheckConstraint(
            "jsonb_typeof(alternatives) = 'array'",
            name="ck_recommendation_snapshots_alternatives",
        ),
    )


class RecommendationFeedback(Base):
    """Ignore / restore state per suggested subject, with a revision."""

    __tablename__ = "recommendation_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    subject_key: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="IGNORED")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("owner_user_id", "subject_key", name="uq_recommendation_feedback_subject"),
        CheckConstraint("state IN ('IGNORED', 'ACTIVE')", name="ck_recommendation_feedback_state"),
        CheckConstraint("revision >= 1", name="ck_recommendation_feedback_revision"),
    )


class RecommendationFeedbackEvent(Base):
    __tablename__ = "recommendation_feedback_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendation_feedback.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    from_state: Mapped[str] = mapped_column(String(16), nullable=False)
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    from_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    to_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('IGNORE', 'RESTORE')", name="ck_recommendation_feedback_action"
        ),
    )
