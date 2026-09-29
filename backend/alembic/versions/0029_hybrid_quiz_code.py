"""allow immutable CODE questions in the existing quiz snapshot table"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0029_hybrid_quiz_code"
down_revision = "0028_codelab_run_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_quiz_questions",
        sa.Column(
            "code_task_revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("codelab_task_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "assessment_quiz_questions",
        sa.Column("code_snapshot", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "assessment_quiz_questions",
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("assessment_quiz_questions", "correct_answer", nullable=True)
    op.alter_column("assessment_quiz_questions", "explanation", nullable=True)
    op.drop_constraint("ck_assessment_question_type", "assessment_quiz_questions", type_="check")
    op.create_check_constraint(
        "ck_assessment_question_type",
        "assessment_quiz_questions",
        "type IN ('SINGLE_CHOICE', 'TRUE_FALSE', 'ORDERING', 'CODE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_assessment_question_type", "assessment_quiz_questions", type_="check")
    op.create_check_constraint(
        "ck_assessment_question_type",
        "assessment_quiz_questions",
        "type IN ('SINGLE_CHOICE', 'TRUE_FALSE', 'ORDERING')",
    )
    op.alter_column("assessment_quiz_questions", "explanation", nullable=False)
    op.alter_column("assessment_quiz_questions", "correct_answer", nullable=False)
    op.drop_column("assessment_quiz_questions", "is_demo")
    op.drop_column("assessment_quiz_questions", "code_snapshot")
    op.drop_column("assessment_quiz_questions", "code_task_revision_id")
