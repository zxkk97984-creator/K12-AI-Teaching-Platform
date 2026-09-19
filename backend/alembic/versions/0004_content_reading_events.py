"""add minimal reading events

Revision ID: 0004_content_reading_events
Revises: 0003_content_library
Create Date: 2026-09-19

Reading events only record *behaviour* (enter/view/select/leave) for one owner.
There is deliberately no mastery, percentage or completion column: scroll and
dwell time must never be stored as evidence of learning.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_content_reading_events"
down_revision = "0003_content_library"
branch_labels = None
depends_on = None

EVENT_KINDS = ("ENTER", "SECTION_VIEW", "BLOCK_VIEW", "SELECT_TEXT", "RESUME", "LEAVE")


def upgrade() -> None:
    op.create_table(
        "content_reading_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapters.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_chapter_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("client_event_id", sa.String(length=64), nullable=False),
        sa.Column("event_kind", sa.String(length=16), nullable=False),
        sa.Column("section_key", sa.String(length=80), nullable=True),
        sa.Column("block_id", sa.String(length=16), nullable=True),
        sa.Column("selected_text_length", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "client_event_id", name="uq_content_reading_user_client"),
        sa.CheckConstraint(
            "event_kind IN ('ENTER', 'SECTION_VIEW', 'BLOCK_VIEW', "
            "'SELECT_TEXT', 'RESUME', 'LEAVE')",
            name="ck_content_reading_event_kind",
        ),
        sa.CheckConstraint(
            "client_event_id ~ '^[A-Za-z0-9._:-]{8,64}$'",
            name="ck_content_reading_client_event_id",
        ),
        sa.CheckConstraint(
            "selected_text_length IS NULL OR "
            "(selected_text_length >= 0 AND selected_text_length <= 500)",
            name="ck_content_reading_selected_length",
        ),
        sa.CheckConstraint(
            "(event_kind <> 'SELECT_TEXT') OR selected_text_length IS NOT NULL",
            name="ck_content_reading_select_requires_length",
        ),
        sa.CheckConstraint(
            "(event_kind = 'SELECT_TEXT') OR selected_text_length IS NULL",
            name="ck_content_reading_length_only_for_select",
        ),
    )
    op.create_index(
        "ix_content_reading_events_user_chapter",
        "content_reading_events",
        ["user_id", "chapter_id", "created_at"],
    )
    op.create_index("ix_content_reading_events_revision", "content_reading_events", ["revision_id"])


def downgrade() -> None:
    op.drop_index("ix_content_reading_events_revision", table_name="content_reading_events")
    op.drop_index("ix_content_reading_events_user_chapter", table_name="content_reading_events")
    op.drop_table("content_reading_events")
