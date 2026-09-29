"""add owner-scoped bookshelf and learning open history

Revision ID: 0020_learning_workbench
Revises: 0019_teaching_scene_snapshot
Create Date: 2026-09-21

The tables in this migration are deliberately small read-model inputs:
bookmarks retain a title snapshot so a withdrawn item can still be removed,
and open events record an explicit open action only. Neither table stores
completion, mastery, or a client supplied owner.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0020_learning_workbench"
down_revision = "0019_teaching_scene_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_bookmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=False),
        sa.Column("target_title", sa.String(length=200), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "target_kind",
            "target_id",
            name="uq_learning_bookmarks_owner_target",
        ),
        sa.CheckConstraint(
            "target_kind IN ('COURSE', 'RESOURCE', 'ANIMATION')",
            name="ck_learning_bookmarks_target_kind",
        ),
        sa.CheckConstraint(
            "length(target_id) BETWEEN 1 AND 160", name="ck_learning_bookmarks_target_id"
        ),
        sa.CheckConstraint(
            "length(target_title) BETWEEN 1 AND 200", name="ck_learning_bookmarks_title"
        ),
    )
    op.create_index(
        "ix_learning_bookmarks_owner_created",
        "learning_bookmarks",
        ["owner_user_id", "created_at"],
    )

    op.create_table(
        "learning_open_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_kind", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=False),
        sa.Column("target_title", sa.String(length=200), nullable=False),
        sa.Column("target_version", sa.String(length=160), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "target_kind IN ('COURSE', 'RESOURCE', 'ANIMATION')",
            name="ck_learning_open_events_target_kind",
        ),
        sa.CheckConstraint(
            "length(target_id) BETWEEN 1 AND 160", name="ck_learning_open_events_target_id"
        ),
        sa.CheckConstraint(
            "length(target_title) BETWEEN 1 AND 200", name="ck_learning_open_events_title"
        ),
    )
    op.create_index(
        "ix_learning_open_events_owner_created",
        "learning_open_events",
        ["owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_open_events_owner_created", table_name="learning_open_events")
    op.drop_table("learning_open_events")
    op.drop_index("ix_learning_bookmarks_owner_created", table_name="learning_bookmarks")
    op.drop_table("learning_bookmarks")
