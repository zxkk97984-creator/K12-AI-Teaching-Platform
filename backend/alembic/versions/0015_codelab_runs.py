"""add owner-scoped codelab drafts, runs, and fixture feedback state"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015_codelab_runs"
down_revision = "0014_codelab_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "codelab_code_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("task_revision", sa.Integer(), nullable=False),
        sa.Column("lesson_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("task_revision >= 1", name="ck_codelab_draft_revision_positive"),
        sa.CheckConstraint("code_sha256 ~ '^[0-9a-f]{64}$'", name="ck_codelab_draft_code_sha256"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["identity_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id", "task_id", "task_revision", name="uq_codelab_draft_owner_task"
        ),
    )
    op.create_index(
        "ix_codelab_code_drafts_owner_user_id", "codelab_code_drafts", ["owner_user_id"]
    )

    op.create_table(
        "codelab_code_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("task_revision", sa.Integer(), nullable=False),
        sa.Column("lesson_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"),
        sa.Column(
            "execution_status", sa.String(length=24), nullable=False, server_default="QUEUED"
        ),
        sa.Column(
            "correctness_status",
            sa.String(length=24),
            nullable=False,
            server_default="NOT_VERIFIED",
        ),
        sa.Column("deterministic_score", sa.Float(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "feedback_status", sa.String(length=24), nullable=False, server_default="UNAVAILABLE"
        ),
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("task_revision >= 1", name="ck_codelab_run_revision_positive"),
        sa.CheckConstraint("code_sha256 ~ '^[0-9a-f]{64}$'", name="ck_codelab_run_code_sha256"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT', "
            "'OUTPUT_LIMIT', 'UNAVAILABLE', 'SYSTEM_ERROR', 'CANCELLED')",
            name="ck_codelab_run_status",
        ),
        sa.CheckConstraint(
            "execution_status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT', "
            "'OUTPUT_LIMIT', 'UNAVAILABLE', 'SYSTEM_ERROR', 'CANCELLED')",
            name="ck_codelab_run_execution_status",
        ),
        sa.CheckConstraint(
            "correctness_status IN ('PASSED', 'PARTIAL', 'FAILED', 'NOT_VERIFIED')",
            name="ck_codelab_run_correctness_status",
        ),
        sa.CheckConstraint(
            "feedback_status IN ('UNAVAILABLE', 'READY', 'FAILED', 'STALE')",
            name="ck_codelab_run_feedback_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["identity_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id", "idempotency_key", name="uq_codelab_run_owner_idempotency"
        ),
    )
    op.create_index("ix_codelab_code_runs_owner_user_id", "codelab_code_runs", ["owner_user_id"])
    op.create_index("ix_codelab_code_runs_status", "codelab_code_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_codelab_code_runs_status", table_name="codelab_code_runs")
    op.drop_index("ix_codelab_code_runs_owner_user_id", table_name="codelab_code_runs")
    op.drop_table("codelab_code_runs")
    op.drop_index("ix_codelab_code_drafts_owner_user_id", table_name="codelab_code_drafts")
    op.drop_table("codelab_code_drafts")
