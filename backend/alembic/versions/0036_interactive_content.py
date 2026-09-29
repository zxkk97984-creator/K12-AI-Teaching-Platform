"""Versioned interactive resources and owner-scoped activity sessions."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0036_interactive_content"
down_revision = "0035_conversation_quiz_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_resource_items_kind", "resource_items", type_="check")
    op.create_check_constraint(
        "ck_resource_items_kind",
        "resource_items",
        "kind IN ('WORD','SLIDES','VIDEO','PDF','IMAGE','INTERACTIVE')",
    )
    op.add_column("resource_items", sa.Column("interactive_purpose", sa.String(16)))
    op.add_column("resource_items", sa.Column("interactive_subject", sa.String(80)))
    op.add_column("resource_items", sa.Column("active_interactive_revision_id", postgresql.UUID()))
    op.create_check_constraint(
        "ck_resource_items_interactive_fields",
        "resource_items",
        "(kind = 'INTERACTIVE' AND interactive_purpose IN ('LESSON','GAME','EXPERIMENT') "
        "AND interactive_subject IS NOT NULL) OR "
        "(kind <> 'INTERACTIVE' AND interactive_purpose IS NULL AND interactive_subject IS NULL "
        "AND active_interactive_revision_id IS NULL)",
    )
    op.create_table(
        "resource_interactive_revisions",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "resource_id",
            postgresql.UUID(),
            sa.ForeignKey("resource_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("package_storage_key", sa.String(400), nullable=False),
        sa.Column("package_sha256", sa.String(64), nullable=False),
        sa.Column("document_storage_key", sa.String(400), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(),
            sa.ForeignKey("identity_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("resource_id", "revision", name="uq_interactive_revision_number"),
        sa.CheckConstraint("revision >= 1", name="ck_interactive_revision_positive"),
    )
    op.create_index(
        "ix_interactive_revisions_resource", "resource_interactive_revisions", ["resource_id"]
    )
    op.create_foreign_key(
        "fk_resource_active_interactive_revision",
        "resource_items",
        "resource_interactive_revisions",
        ["active_interactive_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "resource_interactive_files",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "revision_id",
            postgresql.UUID(),
            sa.ForeignKey("resource_interactive_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.String(300), nullable=False),
        sa.Column("storage_key", sa.String(400), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("revision_id", "relative_path", name="uq_interactive_file_path"),
        sa.CheckConstraint("size_bytes > 0", name="ck_interactive_file_size"),
    )
    op.create_index("ix_interactive_files_revision", "resource_interactive_files", ["revision_id"])
    op.create_table(
        "learning_interactive_sessions",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_id",
            postgresql.UUID(),
            sa.ForeignKey("resource_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(),
            sa.ForeignKey("resource_interactive_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("base_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_scene_id", sa.String(100)),
        sa.Column("game_state", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("host_state", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("game_result", postgresql.JSONB()),
        sa.Column("completion_source", sa.String(24)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('ACTIVE','COMPLETED','ABANDONED')", name="ck_interactive_session_status"
        ),
        sa.CheckConstraint("base_revision >= 0", name="ck_interactive_session_revision"),
    )
    op.create_index(
        "uq_interactive_active_owner_resource",
        "learning_interactive_sessions",
        ["owner_user_id", "resource_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_interactive_sessions_owner",
        "learning_interactive_sessions",
        ["owner_user_id", "created_at"],
    )
    op.create_table(
        "learning_interactive_events",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(),
            sa.ForeignKey("learning_interactive_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("receipt", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("session_id", "client_event_id", name="uq_interactive_event_id"),
    )


def downgrade() -> None:
    op.drop_table("learning_interactive_events")
    op.drop_index(
        "uq_interactive_active_owner_resource", table_name="learning_interactive_sessions"
    )
    op.drop_index("ix_interactive_sessions_owner", table_name="learning_interactive_sessions")
    op.drop_table("learning_interactive_sessions")
    op.drop_index("ix_interactive_files_revision", table_name="resource_interactive_files")
    op.drop_table("resource_interactive_files")
    op.drop_constraint(
        "fk_resource_active_interactive_revision", "resource_items", type_="foreignkey"
    )
    op.drop_index("ix_interactive_revisions_resource", table_name="resource_interactive_revisions")
    op.drop_table("resource_interactive_revisions")
    op.drop_constraint("ck_resource_items_interactive_fields", "resource_items", type_="check")
    op.drop_column("resource_items", "active_interactive_revision_id")
    op.drop_column("resource_items", "interactive_subject")
    op.drop_column("resource_items", "interactive_purpose")
    op.drop_constraint("ck_resource_items_kind", "resource_items", type_="check")
    op.create_check_constraint(
        "ck_resource_items_kind",
        "resource_items",
        "kind IN ('WORD','SLIDES','VIDEO','PDF','IMAGE')",
    )
