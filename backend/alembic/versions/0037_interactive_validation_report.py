"""Persist the structural validation result shown in interactive management."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0037_interactive_validation"
down_revision = "0036_interactive_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resource_interactive_revisions",
        sa.Column(
            "validation_report",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        "UPDATE resource_interactive_revisions SET validation_report = "
        "jsonb_build_object('status','PASS','scope','STRUCTURE_AND_OFFLINE_ASSETS') "
        "WHERE validation_report = '{}'::jsonb"
    )


def downgrade() -> None:
    op.drop_column("resource_interactive_revisions", "validation_report")
