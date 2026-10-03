"""Allow private student quiz groups of up to twenty validated questions."""

from alembic import op

revision = "0044_companion_quiz_capacity"
down_revision = "i_02_a3"
branch_labels = None
depends_on = None


def _capacity(maximum):
    for table, name in (
        ("assessment_quiz_drafts", "ck_assessment_draft_question_count"),
        ("assessment_quiz_sessions", "ck_assessment_quiz_session_question_count"),
    ):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"question_count BETWEEN 1 AND {maximum}")


def upgrade():
    _capacity(20)


def downgrade():
    # PostgreSQL refuses to shrink the constraint if larger groups exist.
    _capacity(5)
