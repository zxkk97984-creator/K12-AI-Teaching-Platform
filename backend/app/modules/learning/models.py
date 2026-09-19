"""Durable policy snapshots and learning evidence (T14)."""

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

EVIDENCE_KINDS = (
    "QUIZ_ANSWERED",
    "CODE_RUN_COMPLETED",
    "PRACTICE_COMPLETED",
    "REFLECTION_SUBMITTED",
    "ACTIVITY_SKIPPED",
)
EVIDENCE_OUTCOMES = (
    "CORRECT",
    "INCORRECT",
    "PASSED",
    "FAILED",
    "COMPLETED",
    "SUBMITTED",
    "SKIPPED",
)
# Only these count as *real activity* for the completion rule; skips never do.
REAL_ACTIVITY_KINDS = (
    "QUIZ_ANSWERED",
    "CODE_RUN_COMPLETED",
    "PRACTICE_COMPLETED",
    "REFLECTION_SUBMITTED",
)
CORRECT_OUTCOMES = ("CORRECT", "PASSED", "COMPLETED")


class LearningPolicySnapshot(Base):
    __tablename__ = "learning_policy_snapshots"

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
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    grade: Mapped[int | None] = mapped_column(Integer)
    preferred_style: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    policy: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "evidence_level IN ('NONE', 'EMERGING', 'SOLID')",
            name="ck_learning_policy_evidence_level",
        ),
        CheckConstraint("input_revision >= 0", name="ck_learning_policy_revision"),
    )


class LearningEvidence(Base):
    __tablename__ = "learning_evidence"

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
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('QUIZ_ANSWERED', 'CODE_RUN_COMPLETED', 'PRACTICE_COMPLETED', "
            "'REFLECTION_SUBMITTED', 'ACTIVITY_SKIPPED')",
            name="ck_learning_evidence_kind",
        ),
        CheckConstraint(
            "outcome IN ('CORRECT', 'INCORRECT', 'PASSED', 'FAILED', 'COMPLETED', "
            "'SUBMITTED', 'SKIPPED')",
            name="ck_learning_evidence_outcome",
        ),
    )


QUIZ_EVIDENCE_KINDS = (
    "QUIZ_ANSWERED",
    "QUIZ_HINT_VIEWED",
    "QUIZ_REVIEW_LINKED",
    "QUIZ_SESSION_COMPLETED",
)
QUIZ_EVIDENCE_OUTCOMES = (
    "CORRECT",
    "INCORRECT",
    "VIEWED",
    "LINKED",
    "COMPLETED",
)


class QuizEvidence(Base):
    """Trusted quiz events (T16) linked to the objective and chapter KPs.

    Rows are written inside the same transaction as the attempt/hint row they
    describe; ``source_event_id`` + ``kind`` is unique so a replay cannot add a
    second event.
    """

    __tablename__ = "learning_quiz_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    quiz_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    objective_id: Mapped[str | None] = mapped_column(String(160))
    knowledge_point_slugs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    thresholds_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("kind", "source_event_id", name="uq_learning_quiz_evidence_event"),
        CheckConstraint(
            "kind IN ('QUIZ_ANSWERED', 'QUIZ_HINT_VIEWED', 'QUIZ_REVIEW_LINKED', "
            "'QUIZ_SESSION_COMPLETED')",
            name="ck_learning_quiz_evidence_kind",
        ),
        CheckConstraint(
            "outcome IN ('CORRECT', 'INCORRECT', 'VIEWED', 'LINKED', 'COMPLETED')",
            name="ck_learning_quiz_evidence_outcome",
        ),
        CheckConstraint(
            "jsonb_typeof(knowledge_point_slugs) = 'array'",
            name="ck_learning_quiz_evidence_kps_array",
        ),
    )


PROJECTED_EVIDENCE_KINDS = (
    "QUIZ_ANSWERED",
    "QUIZ_HINT_VIEWED",
    "QUIZ_REVIEW_LINKED",
    "QUIZ_SESSION_COMPLETED",
    "LESSON_ACTIVITY",
)
OBSERVATION_LEVELS = ("INSUFFICIENT_EVIDENCE", "EMERGING", "CONSISTENT")


class EvidenceItem(Base):
    """Deduplicated projection of one trusted event (T18 K1/K8).

    The trusted rows (``learning_quiz_evidence``, ``learning_evidence``) stay
    authoritative; this table is a derived read model with a stable
    ``dedup_key`` so a repeated projection never adds a second item.
    """

    __tablename__ = "learning_evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    objective_id: Mapped[str | None] = mapped_column(String(160))
    knowledge_point_slugs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_ref: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    projection_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    projected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('QUIZ_ANSWERED', 'QUIZ_HINT_VIEWED', 'QUIZ_REVIEW_LINKED', "
            "'QUIZ_SESSION_COMPLETED', 'LESSON_ACTIVITY')",
            name="ck_learning_evidence_items_kind",
        ),
        CheckConstraint(
            "jsonb_typeof(knowledge_point_slugs) = 'array'",
            name="ck_learning_evidence_items_kps_array",
        ),
        CheckConstraint(
            "jsonb_typeof(source_ref) = 'object'",
            name="ck_learning_evidence_items_source_object",
        ),
    )


class Observation(Base):
    """Versioned qualitative observation (never a mastery percentage)."""

    __tablename__ = "learning_observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), nullable=False
    )
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(24), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    basis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    observation_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    projection_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "subject_key",
            "observation_rule_version",
            "fingerprint",
            name="uq_learning_observations_fingerprint",
        ),
        CheckConstraint(
            "level IN ('INSUFFICIENT_EVIDENCE', 'EMERGING', 'CONSISTENT')",
            name="ck_learning_observations_level",
        ),
        CheckConstraint(
            "subject_kind IN ('OBJECTIVE')", name="ck_learning_observations_subject_kind"
        ),
        CheckConstraint("projection_revision >= 1", name="ck_learning_observations_revision"),
        CheckConstraint("jsonb_typeof(basis) = 'object'", name="ck_learning_observations_basis"),
    )
