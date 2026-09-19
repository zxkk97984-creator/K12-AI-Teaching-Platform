"""add quiz sessions, immutable question snapshots, attempts, hints and review links

Revision ID: 0008_quiz_sessions
Revises: 0007_assessment_quiz
Create Date: 2026-09-19

T16: a quiz session is created from an approved draft and copies the questions
into an immutable snapshot (trigger-guarded), so a later library update can
never change an existing quiz's answers. Attempts, hints and review links are
per-student rows; trusted quiz evidence lives in ``learning_quiz_evidence``.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_quiz_sessions"
down_revision = "0007_assessment_quiz"
branch_labels = None
depends_on = None

IMMUTABLE_FUNCTION = """
CREATE OR REPLACE FUNCTION assessment_quiz_questions_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'assessment_quiz_questions rows are immutable; create a new quiz session';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "assessment_quiz_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_drafts.id", ondelete="SET NULL"),
        ),
        sa.Column("curriculum_revision", sa.String(160), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("grade", sa.Integer()),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_label", sa.String(64), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("max_hints", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_slugs", postgresql.JSONB(), nullable=False),
        sa.Column("scoring_version", sa.String(64), nullable=False),
        sa.Column("thresholds_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("base_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED')", name="ck_assessment_quiz_session_status"
        ),
        sa.CheckConstraint(
            "source_kind IN ('HUMAN_REVIEWED', 'AI_DRAFT')",
            name="ck_assessment_quiz_session_source_kind",
        ),
        sa.CheckConstraint(
            "difficulty IN ('EASY', 'MEDIUM', 'HARD')",
            name="ck_assessment_quiz_session_difficulty",
        ),
        sa.CheckConstraint(
            "question_count BETWEEN 1 AND 5", name="ck_assessment_quiz_session_question_count"
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 5", name="ck_assessment_quiz_session_max_attempts"
        ),
        sa.CheckConstraint(
            "max_hints BETWEEN 1 AND 3", name="ck_assessment_quiz_session_max_hints"
        ),
        sa.CheckConstraint("base_revision >= 0", name="ck_assessment_quiz_session_base_revision"),
        sa.CheckConstraint(
            "status <> 'COMPLETED' OR completed_at IS NOT NULL",
            name="ck_assessment_quiz_session_completed_at",
        ),
    )
    op.create_index(
        "ix_assessment_quiz_sessions_owner_user_id", "assessment_quiz_sessions", ["owner_user_id"]
    )
    op.create_index(
        "ix_assessment_quiz_sessions_chapter_id", "assessment_quiz_sessions", ["chapter_id"]
    )

    op.create_table(
        "assessment_quiz_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question_key", sa.String(80), nullable=False),
        sa.Column("objective_id", sa.String(160), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB()),
        sa.Column("items", postgresql.JSONB()),
        sa.Column("correct_answer", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("hints", postgresql.JSONB(), nullable=False),
        sa.Column("source_refs", postgresql.JSONB(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column(
            "source_draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_drafts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("session_id", "position", name="uq_assessment_question_position"),
        sa.UniqueConstraint("session_id", "question_key", name="uq_assessment_question_key"),
        sa.CheckConstraint(
            "type IN ('SINGLE_CHOICE', 'TRUE_FALSE', 'ORDERING')",
            name="ck_assessment_question_type",
        ),
        sa.CheckConstraint(
            "origin IN ('FIXTURE', 'MODEL_DRAFT', 'TEMPLATE')",
            name="ck_assessment_question_origin",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(hints) = 'array' AND jsonb_array_length(hints) BETWEEN 1 AND 3",
            name="ck_assessment_question_hints",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_refs) = 'array'", name="ck_assessment_question_source_refs"
        ),
    )
    op.create_index(
        "ix_assessment_quiz_questions_session_id", "assessment_quiz_questions", ["session_id"]
    )

    op.create_table(
        "assessment_quiz_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_no", sa.Integer()),
        sa.Column("answer", postgresql.JSONB()),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("is_correct", sa.Boolean()),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("scoring_version", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("owner_user_id", "idempotency_key", name="uq_assessment_attempt_key"),
        sa.UniqueConstraint("question_id", "attempt_no", name="uq_assessment_attempt_number"),
        sa.CheckConstraint(
            "outcome IN ('CORRECT', 'INCORRECT', 'SYSTEM_FAILURE')",
            name="ck_assessment_attempt_outcome",
        ),
        sa.CheckConstraint(
            "(outcome = 'SYSTEM_FAILURE' AND attempt_no IS NULL AND is_correct IS NULL) OR "
            "(outcome <> 'SYSTEM_FAILURE' AND attempt_no IS NOT NULL AND is_correct IS NOT NULL)",
            name="ck_assessment_attempt_shape",
        ),
    )
    op.create_index(
        "ix_assessment_quiz_attempts_session_id", "assessment_quiz_attempts", ["session_id"]
    )
    op.create_index(
        "ix_assessment_quiz_attempts_question_id", "assessment_quiz_attempts", ["question_id"]
    )
    op.create_index(
        "ix_assessment_quiz_attempts_owner_user_id", "assessment_quiz_attempts", ["owner_user_id"]
    )

    op.create_table(
        "assessment_quiz_hint_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("owner_user_id", "idempotency_key", name="uq_assessment_hint_key"),
        sa.UniqueConstraint("question_id", "level", name="uq_assessment_hint_level"),
        sa.CheckConstraint("level BETWEEN 1 AND 3", name="ck_assessment_hint_level"),
    )
    op.create_index(
        "ix_assessment_quiz_hint_events_session_id", "assessment_quiz_hint_events", ["session_id"]
    )
    op.create_index(
        "ix_assessment_quiz_hint_events_question_id", "assessment_quiz_hint_events", ["question_id"]
    )

    op.create_table(
        "assessment_quiz_review_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("objective_id", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False, server_default="INCORRECT"),
        sa.Column(
            "similar_draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_quiz_drafts.id", ondelete="SET NULL"),
        ),
        sa.Column("similar_question_key", sa.String(80)),
        sa.Column("thresholds_version", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "question_id", "owner_user_id", "reason", name="uq_assessment_review_question_reason"
        ),
        sa.CheckConstraint("reason = 'INCORRECT'", name="ck_assessment_review_reason"),
    )
    op.create_index(
        "ix_assessment_quiz_review_links_session_id", "assessment_quiz_review_links", ["session_id"]
    )
    op.create_index(
        "ix_assessment_quiz_review_links_question_id",
        "assessment_quiz_review_links",
        ["question_id"],
    )

    op.create_table(
        "learning_quiz_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quiz_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("objective_id", sa.String(160)),
        sa.Column("knowledge_point_slugs", postgresql.JSONB(), nullable=False),
        sa.Column("thresholds_version", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("kind", "source_event_id", name="uq_learning_quiz_evidence_event"),
        sa.CheckConstraint(
            "kind IN ('QUIZ_ANSWERED', 'QUIZ_HINT_VIEWED', 'QUIZ_REVIEW_LINKED', "
            "'QUIZ_SESSION_COMPLETED')",
            name="ck_learning_quiz_evidence_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('CORRECT', 'INCORRECT', 'VIEWED', 'LINKED', 'COMPLETED')",
            name="ck_learning_quiz_evidence_outcome",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(knowledge_point_slugs) = 'array'",
            name="ck_learning_quiz_evidence_kps_array",
        ),
    )
    op.create_index(
        "ix_learning_quiz_evidence_quiz_session_id", "learning_quiz_evidence", ["quiz_session_id"]
    )
    op.create_index(
        "ix_learning_quiz_evidence_created_at", "learning_quiz_evidence", ["created_at"]
    )

    op.execute(IMMUTABLE_FUNCTION)
    op.execute(
        "CREATE TRIGGER assessment_quiz_questions_immutable "
        "BEFORE UPDATE OR DELETE ON assessment_quiz_questions "
        "FOR EACH ROW EXECUTE FUNCTION assessment_quiz_questions_immutable();"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS assessment_quiz_questions_immutable ON assessment_quiz_questions"
    )
    op.execute("DROP FUNCTION IF EXISTS assessment_quiz_questions_immutable()")
    op.drop_table("learning_quiz_evidence")
    op.drop_table("assessment_quiz_review_links")
    op.drop_table("assessment_quiz_hint_events")
    op.drop_table("assessment_quiz_attempts")
    op.drop_table("assessment_quiz_questions")
    op.drop_table("assessment_quiz_sessions")
