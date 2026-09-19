"""add designer sessions, generation jobs and quiz drafts

Revision ID: 0007_assessment_quiz
Revises: 0006_learning_phase
Create Date: 2026-09-19

T15: the Designer pipeline gets its own session table (physically separate from
``teaching_lesson_sessions``), an audit job table that never stores raw model
JSON, and a quiz draft table whose ``draft`` column carries the answers
server-side while ``student_projection`` stays answer-free.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_assessment_quiz"
down_revision = "0006_learning_phase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_designer_sessions",
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
        sa.Column("curriculum_revision", sa.String(160), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="QUIZ_DRAFT"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("purpose = 'QUIZ_DRAFT'", name="ck_assessment_designer_purpose"),
        sa.CheckConstraint(
            "stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_assessment_designer_stage",
        ),
    )
    op.create_index(
        "ix_assessment_designer_sessions_owner_user_id",
        "assessment_designer_sessions",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_assessment_designer_sessions_chapter_id",
        "assessment_designer_sessions",
        ["chapter_id"],
    )

    op.create_table(
        "assessment_generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "designer_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_designer_sessions.id", ondelete="CASCADE"),
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
        sa.Column("operation", sa.String(32), nullable=False, server_default="QUIZ_DRAFT"),
        sa.Column("status", sa.String(16), nullable=False, server_default="RUNNING"),
        sa.Column("error_code", sa.String(48)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("gateway_mode", sa.String(16), nullable=False),
        sa.Column("gateway_invocation_id", sa.String(64)),
        sa.Column("fixture", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fixture_allowance", postgresql.JSONB()),
        sa.Column("request_summary", postgresql.JSONB(), nullable=False),
        sa.Column("usage", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("operation = 'QUIZ_DRAFT'", name="ck_assessment_job_operation"),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'REJECTED', 'FAILED')",
            name="ck_assessment_job_status",
        ),
    )
    op.create_index(
        "ix_assessment_generation_jobs_owner_user_id",
        "assessment_generation_jobs",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_assessment_generation_jobs_chapter_id",
        "assessment_generation_jobs",
        ["chapter_id"],
    )

    op.create_table(
        "assessment_quiz_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column("curriculum_revision", sa.String(160), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("request_id", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("question_types", postgresql.JSONB(), nullable=False),
        sa.Column("validation_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("validation", postgresql.JSONB(), nullable=False),
        sa.Column("draft", postgresql.JSONB()),
        sa.Column("student_projection", postgresql.JSONB()),
        sa.Column(
            "review_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("job_id", name="uq_assessment_draft_job"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'AUTO_VALIDATED', 'HUMAN_APPROVED')",
            name="ck_assessment_draft_status",
        ),
        sa.CheckConstraint(
            "origin IN ('FIXTURE', 'MODEL_DRAFT', 'TEMPLATE')",
            name="ck_assessment_draft_origin",
        ),
        sa.CheckConstraint(
            "difficulty IN ('EASY', 'MEDIUM', 'HARD')",
            name="ck_assessment_draft_difficulty",
        ),
        sa.CheckConstraint(
            "question_count BETWEEN 1 AND 5", name="ck_assessment_draft_question_count"
        ),
        sa.CheckConstraint(
            "status = 'DRAFT' OR validation_passed", name="ck_assessment_draft_validated"
        ),
        sa.CheckConstraint(
            "status <> 'HUMAN_APPROVED' OR (review_subject_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_assessment_draft_human_requires_reviewer",
        ),
    )
    op.create_index(
        "ix_assessment_quiz_drafts_owner_user_id", "assessment_quiz_drafts", ["owner_user_id"]
    )
    op.create_index(
        "ix_assessment_quiz_drafts_chapter_id", "assessment_quiz_drafts", ["chapter_id"]
    )


def downgrade() -> None:
    op.drop_table("assessment_quiz_drafts")
    op.drop_table("assessment_generation_jobs")
    op.drop_table("assessment_designer_sessions")
