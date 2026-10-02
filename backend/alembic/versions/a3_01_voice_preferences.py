"""Default-off automatic reply narration."""

import sqlalchemy as sa

from alembic import op

revision = "a3_01_voice_preferences"
down_revision = "0043_original_textbooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learner_profiles",
        sa.Column("auto_read_replies", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("learner_profiles", "auto_read_replies")
