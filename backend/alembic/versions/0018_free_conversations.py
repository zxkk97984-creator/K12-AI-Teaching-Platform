"""add free conversation metadata to teaching sessions

Revision ID: 0018_free_conversations
Revises: 0017_knodo_remote_bindings
Create Date: 2026-09-21

Free conversations deliberately share the lesson-session/run/message tables so
they retain the existing owner checks, idempotency and Knodo worker path.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018_free_conversations"
down_revision = "0017_knodo_remote_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "teaching_lesson_sessions",
        "chapter_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "teaching_lesson_sessions",
        "revision_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        nullable=True,
    )
    op.add_column(
        "teaching_lesson_sessions",
        sa.Column(
            "conversation_type", sa.String(length=16), nullable=False, server_default="LESSON"
        ),
    )
    op.add_column("teaching_lesson_sessions", sa.Column("title", sa.String(length=200)))
    op.add_column(
        "teaching_lesson_sessions",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE teaching_lesson_sessions AS s "
            "SET title = c.title "
            "FROM content_chapters AS c "
            "WHERE s.chapter_id = c.id AND s.title IS NULL"
        )
    )
    op.create_check_constraint(
        "ck_teaching_sessions_conversation_type",
        "teaching_lesson_sessions",
        "conversation_type IN ('LESSON', 'FREE')",
    )
    op.create_check_constraint(
        "ck_teaching_sessions_conversation_target",
        "teaching_lesson_sessions",
        "(conversation_type = 'FREE' AND chapter_id IS NULL AND revision_id IS NULL) "
        "OR (conversation_type = 'LESSON' AND chapter_id IS NOT NULL AND revision_id IS NOT NULL)",
    )
    op.create_index(
        "ix_teaching_lesson_sessions_conversation_type",
        "teaching_lesson_sessions",
        ["conversation_type"],
    )
    op.create_index(
        "ix_teaching_lesson_sessions_archived_at",
        "teaching_lesson_sessions",
        ["archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_teaching_lesson_sessions_archived_at", table_name="teaching_lesson_sessions")
    op.drop_index(
        "ix_teaching_lesson_sessions_conversation_type", table_name="teaching_lesson_sessions"
    )
    op.drop_constraint(
        "ck_teaching_sessions_conversation_target", "teaching_lesson_sessions", type_="check"
    )
    op.drop_constraint(
        "ck_teaching_sessions_conversation_type", "teaching_lesson_sessions", type_="check"
    )
    op.drop_column("teaching_lesson_sessions", "archived_at")
    op.drop_column("teaching_lesson_sessions", "title")
    op.drop_column("teaching_lesson_sessions", "conversation_type")
    op.alter_column(
        "teaching_lesson_sessions",
        "revision_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "teaching_lesson_sessions",
        "chapter_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        nullable=False,
    )
