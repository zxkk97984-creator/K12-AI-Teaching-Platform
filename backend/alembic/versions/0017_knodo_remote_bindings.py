"""persist target-scoped Knodo conversation metadata

Revision ID: 0017_knodo_remote_bindings
Revises: 0016_privacy_requests
Create Date: 2026-09-20
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017_knodo_remote_bindings"
down_revision = "0016_privacy_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "teaching_remote_bindings",
        "remote_id",
        existing_type=sa.String(length=120),
        type_=sa.String(length=300),
        existing_nullable=False,
    )
    op.add_column(
        "teaching_remote_bindings",
        sa.Column("remote_scope", sa.String(length=400), nullable=True),
    )
    op.add_column(
        "teaching_remote_bindings",
        sa.Column("remote_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_teaching_remote_bindings_owner_scope",
        "teaching_remote_bindings",
        ["owner_user_id", "remote_scope"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_teaching_remote_bindings_owner_scope",
        table_name="teaching_remote_bindings",
    )
    op.drop_column("teaching_remote_bindings", "remote_metadata")
    op.drop_column("teaching_remote_bindings", "remote_scope")
    op.alter_column(
        "teaching_remote_bindings",
        "remote_id",
        existing_type=sa.String(length=300),
        type_=sa.String(length=120),
        existing_nullable=False,
    )
