"""Persist owner-scoped positions in the two built-in picturebooks."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0033_picturebook_progress"
down_revision = "0032_quiz_favorites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_picturebook_progress",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("story_id", sa.String(length=24), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["identity_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_user_id", "story_id"),
        sa.CheckConstraint("story_id IN ('crow', 'tortoise')", name="ck_picturebook_story_id"),
        sa.CheckConstraint("page_index BETWEEN 0 AND 2", name="ck_picturebook_page_index"),
    )


def downgrade() -> None:
    op.drop_table("learning_picturebook_progress")
