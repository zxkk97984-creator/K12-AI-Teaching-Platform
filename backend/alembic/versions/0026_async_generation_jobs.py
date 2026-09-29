"""queue student Designer jobs and retain their exact request snapshot"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0026_async_generation_jobs"
down_revision = "0025_quiz_answer_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_generation_jobs",
        sa.Column("purpose", sa.String(16), nullable=False, server_default="ADMIN"),
    )
    op.add_column("assessment_generation_jobs", sa.Column("request_id", sa.String(160)))
    op.add_column("assessment_generation_jobs", sa.Column("request_hash", sa.String(64)))
    op.add_column(
        "assessment_generation_jobs",
        sa.Column("request_config", postgresql.JSONB(), nullable=True),
    )
    op.add_column("assessment_generation_jobs", sa.Column("lease_token", sa.String(64)))
    op.add_column(
        "assessment_generation_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assessment_generation_jobs",
        sa.Column("quiz_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_assessment_generation_quiz_session",
        "assessment_generation_jobs",
        "assessment_quiz_sessions",
        ["quiz_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_assessment_generation_jobs_request_hash",
        "assessment_generation_jobs",
        ["request_hash"],
    )
    op.create_check_constraint(
        "ck_assessment_job_purpose",
        "assessment_generation_jobs",
        "purpose IN ('ADMIN', 'STUDENT')",
    )
    op.drop_constraint("ck_assessment_job_status", "assessment_generation_jobs", type_="check")
    op.create_check_constraint(
        "ck_assessment_job_status",
        "assessment_generation_jobs",
        "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'REJECTED', 'FAILED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_assessment_job_status", "assessment_generation_jobs", type_="check")
    op.create_check_constraint(
        "ck_assessment_job_status",
        "assessment_generation_jobs",
        "status IN ('RUNNING', 'SUCCEEDED', 'REJECTED', 'FAILED')",
    )
    op.drop_constraint("ck_assessment_job_purpose", "assessment_generation_jobs", type_="check")
    op.drop_index(
        "ix_assessment_generation_jobs_request_hash",
        table_name="assessment_generation_jobs",
    )
    op.drop_constraint(
        "fk_assessment_generation_quiz_session",
        "assessment_generation_jobs",
        type_="foreignkey",
    )
    for column in (
        "quiz_session_id",
        "lease_expires_at",
        "lease_token",
        "request_config",
        "request_hash",
        "request_id",
        "purpose",
    ):
        op.drop_column("assessment_generation_jobs", column)
