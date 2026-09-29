"""persist the student generation idempotency key"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0023_student_gen_idem"
down_revision = "0022_codelab_workspace_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_generation_jobs", sa.Column("idempotency_key", sa.String(160), nullable=True)
    )
    op.create_index(
        "ix_assessment_generation_jobs_idempotency_key",
        "assessment_generation_jobs",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assessment_generation_jobs_idempotency_key",
        table_name="assessment_generation_jobs",
    )
    op.drop_column("assessment_generation_jobs", "idempotency_key")
