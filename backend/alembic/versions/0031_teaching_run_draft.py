"""Store bounded provisional teaching text for reconnectable SSE."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_teaching_run_draft"
down_revision = "0030_conv_create_idem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teaching_agent_runs", sa.Column("draft_markdown", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("teaching_agent_runs", "draft_markdown")
