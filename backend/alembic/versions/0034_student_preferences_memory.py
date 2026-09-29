"""Store account teacher/pet preferences and identify one primary Markdown note."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0034_student_preferences_memory"
down_revision = "0033_picturebook_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learner_profiles",
        sa.Column("teacher_style", sa.String(16), nullable=False, server_default="AUTO"),
    )
    op.add_column(
        "learner_profiles",
        sa.Column("companion_pet_id", sa.String(32), nullable=False, server_default="shuangling"),
    )
    op.create_check_constraint(
        "ck_learner_profiles_teacher_style",
        "learner_profiles",
        "teacher_style IN ('AUTO', 'GENTLE', 'PLAYFUL', 'PRECISE', 'SOCRATIC')",
    )
    op.create_check_constraint(
        "ck_learner_profiles_companion_pet_id",
        "learner_profiles",
        "companion_pet_id IN ('shuangling', 'anya', 'doraemon', "
        "'kun-like', 'lulu-capybara', 'shinchan')",
    )
    op.add_column(
        "memory_documents",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("""UPDATE memory_documents AS d SET is_primary = TRUE WHERE d.id = (
      SELECT x.id FROM memory_documents x WHERE x.owner_user_id = d.owner_user_id
      AND x.title = '个人记忆.md' ORDER BY x.created_at, x.id LIMIT 1
    )""")
    op.create_index(
        "uq_memory_documents_primary_owner",
        "memory_documents",
        ["owner_user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index("uq_memory_documents_primary_owner", table_name="memory_documents")
    op.drop_column("memory_documents", "is_primary")
    op.drop_constraint("ck_learner_profiles_companion_pet_id", "learner_profiles", type_="check")
    op.drop_constraint("ck_learner_profiles_teacher_style", "learner_profiles", type_="check")
    op.drop_column("learner_profiles", "companion_pet_id")
    op.drop_column("learner_profiles", "teacher_style")
