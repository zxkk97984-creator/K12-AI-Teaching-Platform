"""add scope and purpose to reusable CodeLab workspaces"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0022_codelab_workspace_scope"
down_revision = "0021_memory_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("codelab_code_drafts", sa.Column("scope_key", sa.String(220), nullable=True))
    op.add_column("codelab_code_drafts", sa.Column("revision", sa.Integer(), nullable=True))
    op.execute("UPDATE codelab_code_drafts SET scope_key='standalone' WHERE scope_key IS NULL")
    op.execute("UPDATE codelab_code_drafts SET revision=1 WHERE revision IS NULL")
    op.alter_column("codelab_code_drafts", "scope_key", nullable=False, server_default="standalone")
    op.alter_column("codelab_code_drafts", "revision", nullable=False, server_default="1")
    op.drop_constraint("uq_codelab_draft_owner_task", "codelab_code_drafts", type_="unique")
    op.create_unique_constraint(
        "uq_codelab_draft_owner_task_scope",
        "codelab_code_drafts",
        ["owner_user_id", "task_id", "task_revision", "scope_key"],
    )
    op.create_check_constraint("ck_codelab_draft_revision", "codelab_code_drafts", "revision >= 1")
    op.create_check_constraint(
        "ck_codelab_draft_scope_key", "codelab_code_drafts", "length(scope_key) BETWEEN 1 AND 220"
    )

    op.add_column("codelab_code_runs", sa.Column("scope_key", sa.String(220), nullable=True))
    op.add_column("codelab_code_runs", sa.Column("purpose", sa.String(16), nullable=True))
    op.add_column(
        "codelab_code_runs",
        sa.Column("quiz_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "codelab_code_runs",
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE codelab_code_runs SET scope_key='standalone' WHERE scope_key IS NULL")
    op.execute("UPDATE codelab_code_runs SET purpose='GRADE' WHERE purpose IS NULL")
    op.alter_column("codelab_code_runs", "scope_key", nullable=False, server_default="standalone")
    op.alter_column("codelab_code_runs", "purpose", nullable=False, server_default="GRADE")
    op.create_check_constraint(
        "ck_codelab_run_scope_key", "codelab_code_runs", "length(scope_key) BETWEEN 1 AND 220"
    )
    op.create_check_constraint(
        "ck_codelab_run_purpose", "codelab_code_runs", "purpose IN ('EXAMPLE', 'GRADE')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_codelab_run_purpose", "codelab_code_runs", type_="check")
    op.drop_constraint("ck_codelab_run_scope_key", "codelab_code_runs", type_="check")
    op.drop_column("codelab_code_runs", "question_id")
    op.drop_column("codelab_code_runs", "quiz_session_id")
    op.drop_column("codelab_code_runs", "purpose")
    op.drop_column("codelab_code_runs", "scope_key")
    op.drop_constraint("ck_codelab_draft_scope_key", "codelab_code_drafts", type_="check")
    op.drop_constraint("ck_codelab_draft_revision", "codelab_code_drafts", type_="check")
    op.drop_constraint("uq_codelab_draft_owner_task_scope", "codelab_code_drafts", type_="unique")
    op.create_unique_constraint(
        "uq_codelab_draft_owner_task",
        "codelab_code_drafts",
        ["owner_user_id", "task_id", "task_revision"],
    )
    op.drop_column("codelab_code_drafts", "revision")
    op.drop_column("codelab_code_drafts", "scope_key")
