"""add student-owned Markdown memory documents and context revision

Revision ID: 0021_memory_documents
Revises: 0020_learning_workbench
Create Date: 2026-09-21

Documents are separate from rule-derived memory candidates.  Every mutation
stores an immutable version, and the owner-scoped context state lets teaching
runs reject late results that were created with an older AI-memory allowance.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0021_memory_documents"
down_revision = "0020_learning_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="NOTE"),
        sa.Column("content_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "category IN ('PREFERENCE', 'GOAL', 'INTEREST', 'NOTE')",
            name="ck_memory_documents_category",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_memory_documents_revision"),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 80", name="ck_memory_documents_title"),
        sa.CheckConstraint(
            "char_length(content_markdown) <= 20000", name="ck_memory_documents_content_length"
        ),
    )
    op.create_index(
        "ix_memory_documents_owner_updated",
        "memory_documents",
        ["owner_user_id", "updated_at"],
    )
    op.create_index("ix_memory_documents_owner_user_id", "memory_documents", ["owner_user_id"])

    op.create_table(
        "memory_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("document_id", "revision", name="uq_memory_document_versions_revision"),
        sa.CheckConstraint(
            "category IN ('PREFERENCE', 'GOAL', 'INTEREST', 'NOTE')",
            name="ck_memory_document_versions_category",
        ),
        sa.CheckConstraint(
            "action IN ('CREATE', 'EDIT', 'RESTORE', 'AI_USAGE')",
            name="ck_memory_document_versions_action",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_memory_document_versions_revision"),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 80", name="ck_memory_document_versions_title"
        ),
        sa.CheckConstraint(
            "char_length(content_markdown) <= 20000",
            name="ck_memory_document_versions_content_length",
        ),
    )
    op.create_index(
        "ix_memory_document_versions_owner_document",
        "memory_document_versions",
        ["owner_user_id", "document_id", "revision"],
    )
    op.create_index(
        "ix_memory_document_versions_document_id", "memory_document_versions", ["document_id"]
    )

    op.create_table(
        "memory_context_states",
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision >= 0", name="ck_memory_context_states_revision"),
    )

    op.add_column(
        "teaching_agent_runs",
        sa.Column("memory_context_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_teaching_runs_memory_revision",
        "teaching_agent_runs",
        "memory_context_revision >= 0",
    )
    op.alter_column("memory_documents", "category", server_default=None)
    op.alter_column("memory_documents", "content_markdown", server_default=None)
    op.alter_column("memory_documents", "revision", server_default=None)
    op.alter_column("memory_documents", "ai_enabled", server_default=None)
    op.alter_column("memory_context_states", "revision", server_default=None)
    op.alter_column("teaching_agent_runs", "memory_context_revision", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_teaching_runs_memory_revision", "teaching_agent_runs", type_="check")
    op.drop_column("teaching_agent_runs", "memory_context_revision")
    op.drop_table("memory_context_states")
    op.drop_index(
        "ix_memory_document_versions_owner_document", table_name="memory_document_versions"
    )
    op.drop_index("ix_memory_document_versions_document_id", table_name="memory_document_versions")
    op.drop_table("memory_document_versions")
    op.drop_index("ix_memory_documents_owner_updated", table_name="memory_documents")
    op.drop_index("ix_memory_documents_owner_user_id", table_name="memory_documents")
    op.drop_table("memory_documents")
