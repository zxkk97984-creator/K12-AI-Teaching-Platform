"""Add CodeLab catalogue metadata and owner-scoped favourites."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0040_codelab_catalog_favorites"
down_revision = "0039_student_identity_card"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "codelab_task_catalog",
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("task_revision", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "category IN ('PYTHON_BASICS', 'DATA_PROCESSING', 'ALGORITHMS')",
            name="ck_codelab_task_catalog_category",
        ),
        sa.CheckConstraint(
            "difficulty IN ('EASY', 'MEDIUM', 'HARD')",
            name="ck_codelab_task_catalog_difficulty",
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_codelab_task_catalog_sort_order"),
        sa.CheckConstraint("jsonb_typeof(tags) = 'array'", name="ck_codelab_task_catalog_tags"),
        sa.ForeignKeyConstraint(
            ["task_id", "task_revision"],
            ["codelab_task_revisions.task_id", "codelab_task_revisions.revision"],
            name="fk_codelab_task_catalog_revision",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", "task_revision"),
    )
    op.create_index(
        "ix_codelab_task_catalog_order",
        "codelab_task_catalog",
        ["category", "difficulty", "sort_order", "task_id"],
    )
    op.create_table(
        "codelab_task_favorites",
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("owner_user_id", "task_id"),
    )
    op.create_index(
        "ix_codelab_run_owner_created_id",
        "codelab_code_runs",
        ["owner_user_id", "created_at", "id"],
    )
    op.create_index(
        "ix_codelab_run_owner_task_revision",
        "codelab_code_runs",
        ["owner_user_id", "task_id", "task_revision"],
    )


def downgrade() -> None:
    op.drop_index("ix_codelab_run_owner_task_revision", table_name="codelab_code_runs")
    op.drop_index("ix_codelab_run_owner_created_id", table_name="codelab_code_runs")
    op.drop_table("codelab_task_favorites")
    op.drop_index("ix_codelab_task_catalog_order", table_name="codelab_task_catalog")
    op.drop_table("codelab_task_catalog")
