"""A chapter-backed private group can also belong to a free conversation."""

from alembic import op

revision = "0045_companion_quiz_sources"
down_revision = "0044_companion_quiz_capacity"
branch_labels = None
depends_on = None

TABLES = (
    "assessment_designer_sessions",
    "assessment_generation_jobs",
    "assessment_quiz_drafts",
    "assessment_quiz_sessions",
)


def _sources(chapter_condition):
    for table in TABLES:
        name = f"ck_{table}_source_target"
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name,
            table,
            f"(chapter_id IS NOT NULL AND revision_id IS NOT NULL {chapter_condition}) OR "
            "(chapter_id IS NULL AND revision_id IS NULL AND source_conversation_id IS NOT NULL)",
        )


def upgrade():
    _sources("")


def downgrade():
    _sources("AND source_conversation_id IS NULL")
