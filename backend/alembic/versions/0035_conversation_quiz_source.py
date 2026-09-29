"""Allow a validated tutor message to be the private source of a quiz."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0035_conversation_quiz_source"
down_revision = "0034_student_preferences_memory"
branch_labels = None
depends_on = None

TABLES = (
    "assessment_designer_sessions",
    "assessment_generation_jobs",
    "assessment_quiz_drafts",
    "assessment_quiz_sessions",
)


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "chapter_id", existing_type=postgresql.UUID(), nullable=True)
        op.alter_column(table, "revision_id", existing_type=postgresql.UUID(), nullable=True)
        op.add_column(table, sa.Column("source_conversation_id", postgresql.UUID(), nullable=True))
        op.create_check_constraint(
            f"ck_{table}_source_target",
            table,
            "(chapter_id IS NOT NULL AND revision_id IS NOT NULL "
            "AND source_conversation_id IS NULL) OR "
            "(chapter_id IS NULL AND revision_id IS NULL "
            "AND source_conversation_id IS NOT NULL)",
        )
    for table in ("assessment_generation_jobs", "assessment_quiz_sessions"):
        op.add_column(table, sa.Column("source_message_id", postgresql.UUID(), nullable=True))
        op.create_index(f"ix_{table}_source_conversation_id", table, ["source_conversation_id"])
    op.add_column(
        "assessment_quiz_sessions",
        sa.Column("source_title", sa.String(200), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("assessment_quiz_sessions", "source_title")
    for table in ("assessment_quiz_sessions", "assessment_generation_jobs"):
        op.drop_index(f"ix_{table}_source_conversation_id", table_name=table)
        op.drop_column(table, "source_message_id")
    for table in reversed(TABLES):
        op.drop_constraint(f"ck_{table}_source_target", table, type_="check")
        op.drop_column(table, "source_conversation_id")
        op.alter_column(table, "chapter_id", existing_type=postgresql.UUID(), nullable=False)
        op.alter_column(table, "revision_id", existing_type=postgresql.UUID(), nullable=False)
