"""add persistent teaching sessions, runs, messages and remote bindings

Revision ID: 0005_teaching_runs
Revises: 0004_content_reading_events
Create Date: 2026-09-19

T12: the conversation/run layer. Idempotency and mutual exclusion are database
constraints (unique owner+key, lease token on the run row) so they hold across
processes. Output is stored as a validated card, never as a raw model payload.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_teaching_runs"
down_revision = "0004_content_reading_events"
branch_labels = None
depends_on = None

RUN_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "STALE")


def upgrade() -> None:
    op.create_table(
        "teaching_lesson_sessions",
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
        sa.Column("grade", sa.Integer),
        sa.Column("base_revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("context", postgresql.JSONB, nullable=False),
        sa.Column("fixture_allowance", postgresql.JSONB),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("base_revision >= 0", name="ck_teaching_sessions_base_revision"),
        sa.CheckConstraint(
            "stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_teaching_sessions_stage",
        ),
    )
    op.create_index(
        "ix_teaching_lesson_sessions_owner", "teaching_lesson_sessions", ["owner_user_id"]
    )
    op.create_index(
        "ix_teaching_lesson_sessions_chapter", "teaching_lesson_sessions", ["chapter_id"]
    )

    op.create_table(
        "teaching_agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_lesson_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="QUEUED"),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("gateway_invocation_id", sa.String(64)),
        sa.Column("error_category", sa.String(40)),
        sa.Column("stale_reason", sa.String(80)),
        sa.Column("result_message_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("owner_user_id", "idempotency_key", name="uq_teaching_runs_owner_key"),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE')",
            name="ck_teaching_runs_status",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_teaching_runs_attempt"),
    )
    op.create_index("ix_teaching_agent_runs_session", "teaching_agent_runs", ["session_id"])
    op.create_index("ix_teaching_agent_runs_owner", "teaching_agent_runs", ["owner_user_id"])

    op.create_table(
        "teaching_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_lesson_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_markdown", sa.Text, nullable=False),
        sa.Column("card", postgresql.JSONB),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="ck_teaching_messages_role"),
    )
    op.create_index("ix_teaching_messages_session", "teaching_messages", ["session_id"])
    op.create_index("ix_teaching_messages_owner", "teaching_messages", ["owner_user_id"])
    op.create_index("ix_teaching_messages_created", "teaching_messages", ["created_at"])

    op.create_table(
        "teaching_remote_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teaching_agent_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remote_kind", sa.String(16), nullable=False),
        sa.Column("remote_id", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("remote_kind IN ('FIXTURE', 'KNODO')", name="ck_teaching_bindings_kind"),
    )
    op.create_index(
        "ix_teaching_remote_bindings_owner", "teaching_remote_bindings", ["owner_user_id"]
    )

    # Circular references are added after both tables exist.
    op.create_foreign_key(
        "fk_teaching_messages_run",
        "teaching_messages",
        "teaching_agent_runs",
        ["run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_teaching_runs_result_message",
        "teaching_agent_runs",
        "teaching_messages",
        ["result_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_teaching_runs_result_message", "teaching_agent_runs", type_="foreignkey")
    op.drop_constraint("fk_teaching_messages_run", "teaching_messages", type_="foreignkey")
    op.drop_table("teaching_remote_bindings")
    op.drop_table("teaching_messages")
    op.drop_table("teaching_agent_runs")
    op.drop_table("teaching_lesson_sessions")
