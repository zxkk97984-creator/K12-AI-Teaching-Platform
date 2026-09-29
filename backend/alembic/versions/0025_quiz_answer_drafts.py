"""persist ordinary quiz drafts and the current question position"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0025_quiz_answer_draft"
down_revision = "0024_student_gen_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_quiz_sessions",
        sa.Column("current_position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_assessment_quiz_session_position",
        "assessment_quiz_sessions",
        "current_position >= 0",
    )
    op.create_table(
        "assessment_quiz_answer_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer", postgresql.JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["identity_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["assessment_quiz_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["assessment_quiz_questions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "session_id",
            "question_id",
            name="uq_assessment_answer_draft_owner",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_assessment_answer_draft_revision"),
    )


def downgrade() -> None:
    op.drop_table("assessment_quiz_answer_drafts")
    op.drop_constraint(
        "ck_assessment_quiz_session_position", "assessment_quiz_sessions", type_="check"
    )
    op.drop_column("assessment_quiz_sessions", "current_position")
