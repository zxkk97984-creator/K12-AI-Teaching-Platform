"""Explicit local demonstration visibility for imported learning content."""

import sqlalchemy as sa

from alembic import op

revision = "0042_local_learning_content"
down_revision = "0041_ai_memory"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("content_releases", "resource_items"):
        op.add_column(
            table,
            sa.Column(
                "local_demo_visible", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade():
    for table in ("resource_items", "content_releases"):
        op.drop_column(table, "local_demo_visible")
