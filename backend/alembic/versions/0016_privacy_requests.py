"""add owner-scoped local privacy deletion requests"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016_privacy_requests"
down_revision = "0015_codelab_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "privacy_deletion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="LOCAL_COMPLETED"),
        sa.Column(
            "platform_status", sa.String(length=24), nullable=False, server_default="NOT_REQUESTED"
        ),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('LOCAL_COMPLETED', 'FAILED')", name="ck_privacy_delete_status"
        ),
        sa.CheckConstraint(
            "platform_status IN ('NOT_REQUESTED', 'NOT_VERIFIED', 'PENDING_EXTERNAL', 'COMPLETED')",
            name="ck_privacy_delete_platform_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["identity_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "idempotency_key", name="uq_privacy_delete_owner_key"),
    )
    op.create_index(
        "ix_privacy_deletion_requests_owner_user_id",
        "privacy_deletion_requests",
        ["owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_privacy_deletion_requests_owner_user_id", table_name="privacy_deletion_requests"
    )
    op.drop_table("privacy_deletion_requests")
