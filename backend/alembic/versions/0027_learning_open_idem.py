"""make explicit learning open events safe to retry"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0027_learning_open_idem"
down_revision = "0026_async_generation_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_open_events",
        sa.Column("client_event_id", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_learning_open_events_owner_client",
        "learning_open_events",
        ["owner_user_id", "client_event_id"],
    )
    op.create_check_constraint(
        "ck_learning_open_events_client_id",
        "learning_open_events",
        "client_event_id IS NULL OR client_event_id ~ '^[A-Za-z0-9._:-]{8,64}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_learning_open_events_client_id", "learning_open_events", type_="check")
    op.drop_constraint(
        "uq_learning_open_events_owner_client", "learning_open_events", type_="unique"
    )
    op.drop_column("learning_open_events", "client_event_id")
