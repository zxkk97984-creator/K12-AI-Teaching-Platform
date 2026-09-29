"""add restart-safe async CodeRun leases and request fingerprints"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028_codelab_run_leases"
down_revision = "0027_learning_open_idem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("codelab_code_runs", sa.Column("request_hash", sa.String(64)))
    op.add_column("codelab_code_runs", sa.Column("lease_token", sa.String(64)))
    op.add_column("codelab_code_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("codelab_code_runs", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.create_index("ix_codelab_code_runs_request_hash", "codelab_code_runs", ["request_hash"])


def downgrade() -> None:
    op.drop_index("ix_codelab_code_runs_request_hash", table_name="codelab_code_runs")
    op.drop_column("codelab_code_runs", "started_at")
    op.drop_column("codelab_code_runs", "lease_expires_at")
    op.drop_column("codelab_code_runs", "lease_token")
    op.drop_column("codelab_code_runs", "request_hash")
