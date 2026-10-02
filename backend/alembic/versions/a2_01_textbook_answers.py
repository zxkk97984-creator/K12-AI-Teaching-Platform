"""Private reference answers associated with immutable textbook revisions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a2_01_textbook_answers"
down_revision = "0043_original_textbooks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_textbook_answers",
        sa.Column(
            "chapter_revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("question_id", sa.String(3), primary_key=True),
        sa.Column("question_type", sa.String(20), nullable=False),
        sa.Column("correct_options", postgresql.JSONB(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.CheckConstraint("question_id ~ '^Q0[1-6]$'", name="ck_textbook_answer_id"),
        sa.CheckConstraint(
            "(question_id IN ('Q01', 'Q02') AND question_type = 'SINGLE_CHOICE' "
            "AND jsonb_array_length(correct_options) = 1 "
            'AND correct_options <@ \'["A","B","C","D"]\'::jsonb) OR '
            "(question_id IN ('Q03', 'Q04') AND question_type = 'SHORT_ANSWER' "
            "AND correct_options = '[]'::jsonb) OR "
            "(question_id IN ('Q05', 'Q06') AND question_type = 'PRACTICE' "
            "AND correct_options = '[]'::jsonb)",
            name="ck_textbook_answer_type",
        ),
        sa.CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name="ck_textbook_answer_hash"),
    )


def downgrade():
    op.drop_table("content_textbook_answers")
