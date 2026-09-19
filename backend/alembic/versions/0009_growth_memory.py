"""add evidence projection, versioned observations and revocable memory

Revision ID: 0009_growth_memory
Revises: 0008_quiz_sessions
Create Date: 2026-09-19

T18: the trusted write paths (quiz attempts/hints, lesson events) stay
authoritative. Three derived, owner-scoped stores sit on top:

* ``learning_evidence_items`` — a deduplicated projection of trusted events
  (``dedup_key`` unique, so re-projecting never duplicates an event);
* ``learning_observations`` — versioned *qualitative* observations derived from
  those items (fingerprint unique per owner+subject+rule, previous versions keep
  ``superseded_at``, no percentage field exists);
* ``memory_candidates`` + ``memory_events`` — a student-owned memory state
  machine (CANDIDATE/ACTIVE/DISPUTED/REMOVED) with an append-only history, so an
  edit keeps the previous statement and a forgotten candidate can never be
  re-created by replaying the same derivation.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_growth_memory"
down_revision = "0008_quiz_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_evidence_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dedup_key", sa.String(96), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("objective_id", sa.String(160)),
        sa.Column(
            "knowledge_point_slugs",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_ref", postgresql.JSONB, nullable=False),
        sa.Column("projection_rule_version", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "projected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("dedup_key", name="uq_learning_evidence_items_dedup"),
        sa.CheckConstraint(
            "source_kind IN ('QUIZ_ANSWERED', 'QUIZ_HINT_VIEWED', 'QUIZ_REVIEW_LINKED', "
            "'QUIZ_SESSION_COMPLETED', 'LESSON_ACTIVITY')",
            name="ck_learning_evidence_items_kind",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(knowledge_point_slugs) = 'array'",
            name="ck_learning_evidence_items_kps_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_ref) = 'object'",
            name="ck_learning_evidence_items_source_object",
        ),
    )
    op.create_index(
        "ix_learning_evidence_items_owner_observed",
        "learning_evidence_items",
        ["owner_user_id", "observed_at"],
    )

    op.create_table(
        "learning_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_kind", sa.String(32), nullable=False),
        sa.Column("subject_key", sa.String(200), nullable=False),
        sa.Column("level", sa.String(24), nullable=False),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("basis", postgresql.JSONB, nullable=False),
        sa.Column("observation_rule_version", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("projection_revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "subject_key",
            "observation_rule_version",
            "fingerprint",
            name="uq_learning_observations_fingerprint",
        ),
        sa.CheckConstraint(
            "level IN ('INSUFFICIENT_EVIDENCE', 'EMERGING', 'CONSISTENT')",
            name="ck_learning_observations_level",
        ),
        sa.CheckConstraint(
            "subject_kind IN ('OBJECTIVE')", name="ck_learning_observations_subject_kind"
        ),
        sa.CheckConstraint("projection_revision >= 1", name="ck_learning_observations_revision"),
        sa.CheckConstraint("jsonb_typeof(basis) = 'object'", name="ck_learning_observations_basis"),
    )
    op.create_index(
        "ix_learning_observations_owner_subject",
        "learning_observations",
        ["owner_user_id", "subject_key"],
    )

    op.create_table(
        "memory_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="CANDIDATE"),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column(
            "content",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "basis_evidence_ids",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "basis_counts",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("derivation_key", sa.String(96), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False, server_default="RULE_DERIVED"),
        sa.Column("derivation_rule_version", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "owner_user_id", "derivation_key", name="uq_memory_candidates_derivation"
        ),
        sa.CheckConstraint(
            "status IN ('CANDIDATE', 'ACTIVE', 'DISPUTED', 'REMOVED')",
            name="ck_memory_candidates_status",
        ),
        sa.CheckConstraint(
            "kind IN ('STUDY_STRATEGY', 'PREFERENCE')", name="ck_memory_candidates_kind"
        ),
        sa.CheckConstraint("origin = 'RULE_DERIVED'", name="ck_memory_candidates_origin"),
        sa.CheckConstraint("revision >= 1", name="ck_memory_candidates_revision"),
        sa.CheckConstraint(
            "jsonb_typeof(basis_evidence_ids) = 'array'",
            name="ck_memory_candidates_basis_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(content) = 'object'", name="ck_memory_candidates_content_object"
        ),
    )

    op.create_table(
        "memory_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=False),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("from_revision", sa.Integer, nullable=False),
        sa.Column("to_revision", sa.Integer, nullable=False),
        sa.Column("statement_before", sa.Text),
        sa.Column("statement_after", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("actor", sa.String(16), nullable=False, server_default="STUDENT"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "action IN ('CREATE', 'CONFIRM', 'DISPUTE', 'EDIT', 'FORGET')",
            name="ck_memory_events_action",
        ),
        sa.CheckConstraint("actor = 'STUDENT'", name="ck_memory_events_actor"),
    )
    op.create_index(
        "ix_memory_events_candidate_created", "memory_events", ["candidate_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_memory_events_candidate_created", table_name="memory_events")
    op.drop_table("memory_events")
    op.drop_table("memory_candidates")
    op.drop_index("ix_learning_observations_owner_subject", table_name="learning_observations")
    op.drop_table("learning_observations")
    op.drop_index("ix_learning_evidence_items_owner_observed", table_name="learning_evidence_items")
    op.drop_table("learning_evidence_items")
