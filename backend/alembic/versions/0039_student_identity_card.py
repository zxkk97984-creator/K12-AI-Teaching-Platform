"""Add student display names and private account avatars."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0039_student_identity_card"
down_revision = "0038_primary_memory_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("learner_profiles", sa.Column("nickname", sa.String(24), nullable=True))
    op.add_column("learner_profiles", sa.Column("avatar_sha256", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_learner_profiles_nickname",
        "learner_profiles",
        "nickname IS NULL OR char_length(nickname) BETWEEN 1 AND 24",
    )
    op.create_check_constraint(
        "ck_learner_profiles_avatar_sha256",
        "learner_profiles",
        "avatar_sha256 IS NULL OR avatar_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_table(
        "identity_profile_avatars",
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("image_png", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "octet_length(image_png) BETWEEN 1 AND 1048576",
            name="ck_profile_avatar_image_size",
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_profile_avatar_sha256"),
    )


def downgrade() -> None:
    op.drop_table("identity_profile_avatars")
    op.drop_constraint("ck_learner_profiles_avatar_sha256", "learner_profiles", type_="check")
    op.drop_constraint("ck_learner_profiles_nickname", "learner_profiles", type_="check")
    op.drop_column("learner_profiles", "avatar_sha256")
    op.drop_column("learner_profiles", "nickname")
