"""Keep lesson viewing independent of activity completion.

Revision ID: a6_01_viewed_state
Revises: 0043_original_textbooks
"""

import sqlalchemy as sa

from alembic import op

revision = "a6_01_viewed_state"
down_revision = "0043_original_textbooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_interactive_sessions",
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learning_interactive_sessions", "viewed_at")
