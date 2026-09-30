"""Versioned teacher registry and account-owned automatic memory."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0041_ai_memory"
down_revision = "0040_codelab_catalog_favorites"
branch_labels = None
depends_on = None


def owner(primary=False):
    return sa.Column(
        "owner_user_id",
        pg.UUID(as_uuid=True),
        sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
        primary_key=primary,
        nullable=False,
    )


def uid():
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def stamp(name="updated_at"):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table(
        "ai_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("data", pg.JSONB(), nullable=False),
        stamp(),
    )
    op.create_table(
        "personal_memory_states",
        owner(True),
        sa.Column("auto_enabled", sa.Boolean(), nullable=False),
        sa.Column("use_enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_revision", sa.Integer(), nullable=False),
        sa.Column("history_after", sa.DateTime(timezone=True)),
        sa.Column("lease_token", pg.UUID(as_uuid=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
        stamp("created_at"),
    )
    op.create_table(
        "personal_memory_items",
        uid(),
        owner(),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("manual", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("sources", pg.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        stamp(),
        sa.UniqueConstraint("owner_user_id", "key", name="uq_personal_memory_key"),
    )
    op.create_index(
        "ix_personal_memory_items_owner_user_id", "personal_memory_items", ["owner_user_id"]
    )
    op.create_table(
        "personal_memory_events",
        uid(),
        owner(),
        sa.Column(
            "item_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("personal_memory_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        stamp("created_at"),
        sa.UniqueConstraint("item_id", "revision", name="uq_personal_memory_event"),
    )
    op.create_index(
        "ix_personal_memory_events_owner_user_id", "personal_memory_events", ["owner_user_id"]
    )
    op.create_table(
        "personal_memory_tasks",
        uid(),
        owner(),
        sa.Column("source_run_id", sa.String(40), nullable=False),
        sa.Column("session_id", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(80)),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_token", pg.UUID(as_uuid=True)),
        stamp("available_at"),
        stamp("created_at"),
        stamp(),
        sa.UniqueConstraint(
            "owner_user_id", "source_run_id", name="uq_personal_memory_task_source"
        ),
    )
    op.create_index(
        "ix_personal_memory_tasks_owner_user_id", "personal_memory_tasks", ["owner_user_id"]
    )
    op.create_index("ix_personal_memory_tasks_status", "personal_memory_tasks", ["status"])
    op.create_table(
        "personal_memory_summaries",
        uid(),
        owner(),
        sa.Column("session_id", sa.String(40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        stamp(),
        sa.UniqueConstraint("owner_user_id", "session_id", name="uq_personal_memory_summary"),
    )
    op.create_index(
        "ix_personal_memory_summaries_owner_user_id", "personal_memory_summaries", ["owner_user_id"]
    )
    op.add_column("teaching_lesson_sessions", sa.Column("teacher_snapshot", pg.JSONB()))


def downgrade():
    op.drop_column("teaching_lesson_sessions", "teacher_snapshot")
    for name in [
        "personal_memory_summaries",
        "personal_memory_tasks",
        "personal_memory_events",
        "personal_memory_items",
        "personal_memory_states",
        "ai_configurations",
    ]:
        op.drop_table(name)
