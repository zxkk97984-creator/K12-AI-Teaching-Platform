"""Durable Designer sessions, generation jobs and quiz drafts (T15).

Isolation rule (G1/G10): a Designer session is its own row in
``assessment_designer_sessions``. It is never a ``teaching_lesson_sessions``
row, so a Tutor conversation can never be resumed or reused as designer
context, and vice versa.

Answer rule (G4): ``assessment_quiz_drafts.draft`` holds the validated payload
including answers/explanation/hints and stays server-side; only
``student_projection`` (no answers, no explanation, no hint text) may leave the
process.
"""

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

DRAFT_STATUSES = ("DRAFT", "AUTO_VALIDATED", "HUMAN_APPROVED")
DRAFT_ORIGINS = ("FIXTURE", "MODEL_DRAFT", "TEMPLATE")
JOB_STATUSES = ("RUNNING", "SUCCEEDED", "REJECTED", "FAILED")


class DesignerSession(Base):
    __tablename__ = "assessment_designer_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    curriculum_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="QUIZ_DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("purpose = 'QUIZ_DRAFT'", name="ck_assessment_designer_purpose"),
        CheckConstraint(
            "stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_assessment_designer_stage",
        ),
    )


class GenerationJob(Base):
    """Audit row for one Designer call. Never stores the raw model payload."""

    __tablename__ = "assessment_generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    designer_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_designer_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(32), nullable=False, default="QUIZ_DRAFT")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING")
    error_code: Mapped[str | None] = mapped_column(String(48))
    error_detail: Mapped[str | None] = mapped_column(Text)
    gateway_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    gateway_invocation_id: Mapped[str | None] = mapped_column(String(64))
    fixture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fixture_allowance: Mapped[dict | None] = mapped_column(JSONB)
    request_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("operation = 'QUIZ_DRAFT'", name="ck_assessment_job_operation"),
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'REJECTED', 'FAILED')",
            name="ck_assessment_job_status",
        ),
    )


class QuizDraft(Base):
    __tablename__ = "assessment_quiz_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    curriculum_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    question_types: Mapped[list] = mapped_column(JSONB, nullable=False)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation: Mapped[dict] = mapped_column(JSONB, nullable=False)
    draft: Mapped[dict | None] = mapped_column(JSONB)
    student_projection: Mapped[dict | None] = mapped_column(JSONB)
    review_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("job_id", name="uq_assessment_draft_job"),
        CheckConstraint(
            "status IN ('DRAFT', 'AUTO_VALIDATED', 'HUMAN_APPROVED')",
            name="ck_assessment_draft_status",
        ),
        CheckConstraint(
            "origin IN ('FIXTURE', 'MODEL_DRAFT', 'TEMPLATE')", name="ck_assessment_draft_origin"
        ),
        CheckConstraint(
            "difficulty IN ('EASY', 'MEDIUM', 'HARD')", name="ck_assessment_draft_difficulty"
        ),
        CheckConstraint(
            "question_count BETWEEN 1 AND 5", name="ck_assessment_draft_question_count"
        ),
        # AUTO_VALIDATED and HUMAN_APPROVED both require the deterministic rules.
        CheckConstraint(
            "status = 'DRAFT' OR validation_passed", name="ck_assessment_draft_validated"
        ),
        # HUMAN_APPROVED can only exist with a real reviewer subject and time.
        CheckConstraint(
            "status <> 'HUMAN_APPROVED' OR (review_subject_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_assessment_draft_human_requires_reviewer",
        ),
    )


QUIZ_SESSION_STATUSES = ("ACTIVE", "COMPLETED")
QUIZ_SOURCE_KINDS = ("HUMAN_REVIEWED", "AI_DRAFT")
ATTEMPT_OUTCOMES = ("CORRECT", "INCORRECT", "SYSTEM_FAILURE")


class QuizSession(Base):
    """One student's immutable quiz snapshot (T16 H1/H2)."""

    __tablename__ = "assessment_quiz_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_quiz_drafts.id", ondelete="SET NULL")
    )
    curriculum_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    grade: Mapped[int | None] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_label: Mapped[str] = mapped_column(String(64), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hints: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_point_slugs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scoring_version: Mapped[str] = mapped_column(String(64), nullable=False)
    thresholds_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED')", name="ck_assessment_quiz_session_status"
        ),
        CheckConstraint(
            "source_kind IN ('HUMAN_REVIEWED', 'AI_DRAFT')",
            name="ck_assessment_quiz_session_source_kind",
        ),
        CheckConstraint(
            "difficulty IN ('EASY', 'MEDIUM', 'HARD')",
            name="ck_assessment_quiz_session_difficulty",
        ),
        CheckConstraint(
            "question_count BETWEEN 1 AND 5", name="ck_assessment_quiz_session_question_count"
        ),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 5", name="ck_assessment_quiz_session_max_attempts"
        ),
        CheckConstraint("max_hints BETWEEN 1 AND 3", name="ck_assessment_quiz_session_max_hints"),
        CheckConstraint("base_revision >= 0", name="ck_assessment_quiz_session_base_revision"),
        CheckConstraint(
            "status <> 'COMPLETED' OR completed_at IS NOT NULL",
            name="ck_assessment_quiz_session_completed_at",
        ),
    )


class QuizQuestion(Base):
    """Immutable question snapshot. Answers live here, server-side only."""

    __tablename__ = "assessment_quiz_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    question_key: Mapped[str] = mapped_column(String(80), nullable=False)
    objective_id: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSONB)
    items: Mapped[list | None] = mapped_column(JSONB)
    correct_answer: Mapped[object] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    hints: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    source_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_quiz_drafts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_assessment_question_position"),
        UniqueConstraint("session_id", "question_key", name="uq_assessment_question_key"),
        CheckConstraint(
            "type IN ('SINGLE_CHOICE', 'TRUE_FALSE', 'ORDERING')",
            name="ck_assessment_question_type",
        ),
        CheckConstraint(
            "origin IN ('FIXTURE', 'MODEL_DRAFT', 'TEMPLATE')",
            name="ck_assessment_question_origin",
        ),
        CheckConstraint(
            "jsonb_typeof(hints) = 'array' AND jsonb_array_length(hints) BETWEEN 1 AND 3",
            name="ck_assessment_question_hints",
        ),
        CheckConstraint(
            "jsonb_typeof(source_refs) = 'array'",
            name="ck_assessment_question_source_refs",
        ),
    )


class QuizAttempt(Base):
    """One scored attempt (or one honest system-failure record)."""

    __tablename__ = "assessment_quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_no: Mapped[int | None] = mapped_column(Integer)
    answer: Mapped[object | None] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    scoring_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_assessment_attempt_key"),
        UniqueConstraint("question_id", "attempt_no", name="uq_assessment_attempt_number"),
        CheckConstraint(
            "outcome IN ('CORRECT', 'INCORRECT', 'SYSTEM_FAILURE')",
            name="ck_assessment_attempt_outcome",
        ),
        CheckConstraint(
            "(outcome = 'SYSTEM_FAILURE' AND attempt_no IS NULL AND is_correct IS NULL) OR "
            "(outcome <> 'SYSTEM_FAILURE' AND attempt_no IS NOT NULL AND is_correct IS NOT NULL)",
            name="ck_assessment_attempt_shape",
        ),
    )


class QuizHintEvent(Base):
    """One released hint level per question (max three, idempotent)."""

    __tablename__ = "assessment_quiz_hint_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_assessment_hint_key"),
        UniqueConstraint("question_id", "level", name="uq_assessment_hint_level"),
        CheckConstraint("level BETWEEN 1 AND 3", name="ck_assessment_hint_level"),
    )


class QuizReviewLink(Base):
    """Incorrect answer → review source link (QA20). Never cross-student."""

    __tablename__ = "assessment_quiz_review_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    objective_id: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False, default="INCORRECT")
    similar_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_quiz_drafts.id", ondelete="SET NULL")
    )
    similar_question_key: Mapped[str | None] = mapped_column(String(80))
    thresholds_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "question_id", "owner_user_id", "reason", name="uq_assessment_review_question_reason"
        ),
        CheckConstraint("reason = 'INCORRECT'", name="ck_assessment_review_reason"),
    )
