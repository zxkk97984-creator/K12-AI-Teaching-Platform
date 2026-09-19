"""create local identity, sessions, profiles and login attempts

Revision ID: 0001_identity
Revises:
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('student', 'admin')", name="ck_identity_users_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_identity_users_username"),
    )
    op.create_index("ix_identity_users_username", "identity_users", ["username"], unique=False)

    op.create_table(
        "learner_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("grade", sa.Integer(), nullable=True),
        sa.Column("preferred_style", sa.String(length=32), nullable=False, server_default="AUTO"),
        sa.Column(
            "interests",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "proactive_guidance_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "voice_preference", sa.String(length=32), nullable=False, server_default="DISABLED"
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_learner_profiles_stage",
        ),
        sa.CheckConstraint(
            "grade IS NULL OR (grade BETWEEN 1 AND 12)", name="ck_learner_profiles_grade"
        ),
        sa.CheckConstraint(
            "grade IS NULL OR stage IS NOT NULL", name="ck_learner_profiles_grade_requires_stage"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_learner_profiles_revision"),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=False)
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "failed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_login_attempts_username_hash", "login_attempts", ["username_hash"], unique=False
    )
    op.create_index("ix_login_attempts_failed_at", "login_attempts", ["failed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_login_attempts_failed_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_username_hash", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("learner_profiles")
    op.drop_index("ix_identity_users_username", table_name="identity_users")
    op.drop_table("identity_users")
