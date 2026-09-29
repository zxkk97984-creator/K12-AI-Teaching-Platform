"""persist the send-time teaching scene snapshot

Revision ID: 0019_teaching_scene_snapshot
Revises: 0018_free_conversations
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019_teaching_scene_snapshot"
down_revision = "0018_free_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teaching_agent_runs",
        sa.Column("scene_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("teaching_agent_runs", "scene_snapshot")
