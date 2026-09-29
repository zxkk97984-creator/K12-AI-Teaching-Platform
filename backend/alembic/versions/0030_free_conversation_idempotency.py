"""make free conversation creation retry-safe"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0030_conv_create_idem"
down_revision = "0029_hybrid_quiz_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teaching_lesson_sessions",
        sa.Column("creation_key", sa.String(160), nullable=True),
    )
    op.create_unique_constraint(
        "uq_teaching_session_creation_key",
        "teaching_lesson_sessions",
        ["owner_user_id", "creation_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_teaching_session_creation_key", "teaching_lesson_sessions", type_="unique"
    )
    op.drop_column("teaching_lesson_sessions", "creation_key")
