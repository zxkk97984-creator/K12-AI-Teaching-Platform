"""add event-driven recommendation snapshots and student feedback

Revision ID: 0010_recommendation
Revises: 0009_growth_memory
Create Date: 2026-09-19

T19: one next-step decision per student, stored as a versioned snapshot.

* ``recommendation_snapshots`` — written only by an event (tutor run) or an
  explicit refresh; ``(owner, inputs_hash)`` unique so the same inputs never
  create a second row, and ``(owner, source_revision)`` stays monotonic.
* ``recommendation_feedback`` + ``recommendation_feedback_events`` — the
  student's ignore/restore state with a revision for stale-write rejection and
  an append-only history.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_recommendation"
down_revision = "0009_growth_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_revision", sa.Integer, nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("thresholds_version", sa.String(64), nullable=False),
        sa.Column("primary_item", postgresql.JSONB, nullable=False),
        sa.Column(
            "alternatives", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("basis", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inputs_hash", sa.String(64), nullable=False),
        sa.Column("effect_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "owner_user_id", "source_revision", name="uq_recommendation_snapshots_revision"
        ),
        sa.UniqueConstraint(
            "owner_user_id", "inputs_hash", name="uq_recommendation_snapshots_inputs"
        ),
        sa.CheckConstraint("source_revision >= 1", name="ck_recommendation_snapshots_revision"),
        sa.CheckConstraint(
            "jsonb_typeof(primary_item) = 'object'",
            name="ck_recommendation_snapshots_primary",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(alternatives) = 'array'",
            name="ck_recommendation_snapshots_alternatives",
        ),
    )
    op.create_index(
        "ix_recommendation_snapshots_owner_created",
        "recommendation_snapshots",
        ["owner_user_id", "created_at"],
    )

    op.create_table(
        "recommendation_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_key", sa.String(200), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="IGNORED"),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("reason", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "owner_user_id", "subject_key", name="uq_recommendation_feedback_subject"
        ),
        sa.CheckConstraint(
            "state IN ('IGNORED', 'ACTIVE')", name="ck_recommendation_feedback_state"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_recommendation_feedback_revision"),
    )

    op.create_table(
        "recommendation_feedback_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "feedback_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recommendation_feedback.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("from_state", sa.String(16), nullable=False),
        sa.Column("to_state", sa.String(16), nullable=False),
        sa.Column("from_revision", sa.Integer, nullable=False),
        sa.Column("to_revision", sa.Integer, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "action IN ('IGNORE', 'RESTORE')", name="ck_recommendation_feedback_action"
        ),
    )
    op.create_index(
        "ix_recommendation_feedback_events_feedback",
        "recommendation_feedback_events",
        ["feedback_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_feedback_events_feedback", table_name="recommendation_feedback_events"
    )
    op.drop_table("recommendation_feedback_events")
    op.drop_table("recommendation_feedback")
    op.drop_index(
        "ix_recommendation_snapshots_owner_created", table_name="recommendation_snapshots"
    )
    op.drop_table("recommendation_snapshots")
