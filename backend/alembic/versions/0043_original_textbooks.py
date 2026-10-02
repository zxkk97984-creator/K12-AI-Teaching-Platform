"""Add optional, student-safe metadata for complete original textbooks."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0043_original_textbooks"
down_revision = "0042_local_learning_content"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("content_courses", sa.Column("textbook", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("content_courses", "textbook")
