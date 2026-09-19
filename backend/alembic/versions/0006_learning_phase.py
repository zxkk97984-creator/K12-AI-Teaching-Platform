"""add lesson phase/lifecycle state, policy snapshots and learning evidence

Revision ID: 0006_learning_phase
Revises: 0005_teaching_runs
Create Date: 2026-09-19

T14: phase (pedagogical position) is stored next to - not inside - the run
lifecycle. Policy snapshots are immutable rows: a new snapshot supersedes the
old one, so a late run bound to an old snapshot can be rejected as STALE.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_learning_phase"
down_revision = "0005_teaching_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teaching_lesson_sessions",
        sa.Column("phase", sa.String(16), nullable=False, server_default="ORIENT"),
    )
    op.add_column(
        "teaching_lesson_sessions",
        sa.Column("lifecycle", sa.String(16), nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "teaching_lesson_sessions",
        sa.Column("phase_revision", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "teaching_lesson_sessions", sa.Column("policy_snapshot_id", postgresql.UUID(as_uuid=True))
    )
    op.create_check_constraint(
        "ck_teaching_sessions_phase",
        "teaching_lesson_sessions",
        "phase IN ('ORIENT', 'EXPLAIN', 'CHECK', 'PRACTICE', 'REFLECT', 'COMPLETED')",
    )
    op.create_check_constraint(
        "ck_teaching_sessions_lifecycle",
        "teaching_lesson_sessions",
        "lifecycle IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'STALE')",
    )
    op.create_check_constraint(
        "ck_teaching_sessions_phase_revision",
        "teaching_lesson_sessions",
        "phase_revision >= 0",
    )

    op.add_column(
        "teaching_agent_runs",
        sa.Column("event", sa.String(24), nullable=False, server_default="ASK"),
    )
    op.add_column(
        "teaching_agent_runs", sa.Column("policy_snapshot_id", postgresql.UUID(as_uuid=True))
    )

    op.create_table(
        "learning_policy_snapshots",
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
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("grade", sa.Integer),
        sa.Column("preferred_style", sa.String(32), nullable=False),
        sa.Column("evidence_level", sa.String(16), nullable=False),
        sa.Column("input_revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("policy", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "evidence_level IN ('NONE', 'EMERGING', 'SOLID')",
            name="ck_learning_policy_evidence_level",
        ),
        sa.CheckConstraint("input_revision >= 0", name="ck_learning_policy_revision"),
    )
    op.create_index(
        "ix_learning_policy_snapshots_session", "learning_policy_snapshots", ["session_id"]
    )

    op.create_table(
        "learning_evidence",
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
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reference", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('QUIZ_ANSWERED', 'CODE_RUN_COMPLETED', 'PRACTICE_COMPLETED', "
            "'REFLECTION_SUBMITTED', 'ACTIVITY_SKIPPED')",
            name="ck_learning_evidence_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('CORRECT', 'INCORRECT', 'PASSED', 'FAILED', 'COMPLETED', "
            "'SUBMITTED', 'SKIPPED')",
            name="ck_learning_evidence_outcome",
        ),
    )
    op.create_index("ix_learning_evidence_session", "learning_evidence", ["session_id"])
    op.create_index("ix_learning_evidence_created", "learning_evidence", ["created_at"])

    op.create_table(
        "teaching_phase_events",
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
        sa.Column("event", sa.String(24), nullable=False),
        sa.Column("from_phase", sa.String(16), nullable=False),
        sa.Column("to_phase", sa.String(16), nullable=False),
        sa.Column("lifecycle", sa.String(16), nullable=False),
        sa.Column("phase_revision", sa.Integer, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_teaching_phase_events_session", "teaching_phase_events", ["session_id"])


def downgrade() -> None:
    op.drop_table("teaching_phase_events")
    op.drop_table("learning_evidence")
    op.drop_table("learning_policy_snapshots")
    op.drop_constraint(
        "ck_teaching_sessions_phase_revision", "teaching_lesson_sessions", type_="check"
    )
    op.drop_constraint("ck_teaching_sessions_lifecycle", "teaching_lesson_sessions", type_="check")
    op.drop_constraint("ck_teaching_sessions_phase", "teaching_lesson_sessions", type_="check")
    op.drop_column("teaching_lesson_sessions", "policy_snapshot_id")
    op.drop_column("teaching_lesson_sessions", "phase_revision")
    op.drop_column("teaching_lesson_sessions", "lifecycle")
    op.drop_column("teaching_lesson_sessions", "phase")
    op.drop_column("teaching_agent_runs", "policy_snapshot_id")
    op.drop_column("teaching_agent_runs", "event")
