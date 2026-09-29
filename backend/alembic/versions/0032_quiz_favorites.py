"""Persist student practice favorites on owned quiz sessions."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0032_quiz_favorites"
down_revision = "0031_teaching_run_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_quiz_sessions",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("assessment_quiz_sessions", "is_favorite")
