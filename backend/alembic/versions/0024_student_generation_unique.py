"""enforce owner-scoped student generation idempotency"""

from __future__ import annotations

from alembic import op

revision = "0024_student_gen_unique"
down_revision = "0023_student_gen_idem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_assessment_generation_owner_key",
        "assessment_generation_jobs",
        ["owner_user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_assessment_generation_owner_key",
        "assessment_generation_jobs",
        type_="unique",
    )
