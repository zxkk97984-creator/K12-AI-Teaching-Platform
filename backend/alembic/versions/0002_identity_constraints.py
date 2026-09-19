"""add identity database constraints

Revision ID: 0002_identity_constraints
Revises: 0001_identity
Create Date: 2026-09-18
"""

from __future__ import annotations

from alembic import op

revision = "0002_identity_constraints"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_identity_users_username",
        "identity_users",
        "username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'",
    )
    op.create_check_constraint(
        "ck_auth_sessions_token_hash_sha256",
        "auth_sessions",
        "token_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_auth_sessions_expiry_after_creation",
        "auth_sessions",
        "expires_at > created_at",
    )
    op.create_check_constraint(
        "ck_learner_profiles_preferred_style",
        "learner_profiles",
        "preferred_style IN ('AUTO', 'EXAMPLE', 'VISUAL', 'STORY', 'STEP_BY_STEP', 'CODE')",
    )
    op.create_check_constraint(
        "ck_learner_profiles_voice_preference",
        "learner_profiles",
        "voice_preference IN ('DISABLED', 'INPUT_ONLY', 'OUTPUT_ONLY', 'INPUT_AND_OUTPUT')",
    )
    op.create_check_constraint(
        "ck_learner_profiles_interests_array",
        "learner_profiles",
        "jsonb_typeof(interests) = 'array'",
    )
    op.create_check_constraint(
        "ck_login_attempts_username_hash_sha256",
        "login_attempts",
        "username_hash ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_login_attempts_username_hash_sha256", "login_attempts", type_="check")
    op.drop_constraint("ck_learner_profiles_interests_array", "learner_profiles", type_="check")
    op.drop_constraint("ck_learner_profiles_voice_preference", "learner_profiles", type_="check")
    op.drop_constraint("ck_learner_profiles_preferred_style", "learner_profiles", type_="check")
    op.drop_constraint("ck_auth_sessions_expiry_after_creation", "auth_sessions", type_="check")
    op.drop_constraint("ck_auth_sessions_token_hash_sha256", "auth_sessions", type_="check")
    op.drop_constraint("ck_identity_users_username", "identity_users", type_="check")
