from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(enum.StrEnum):
    STUDENT = "student"
    ADMIN = "admin"


class Stage(enum.StrEnum):
    PRIMARY_LOWER = "PRIMARY_LOWER"
    PRIMARY_UPPER = "PRIMARY_UPPER"
    JUNIOR = "JUNIOR"
    SENIOR = "SENIOR"


class PreferredStyle(enum.StrEnum):
    AUTO = "AUTO"
    EXAMPLE = "EXAMPLE"
    VISUAL = "VISUAL"
    STORY = "STORY"
    STEP_BY_STEP = "STEP_BY_STEP"
    CODE = "CODE"


class TeacherStyle(enum.StrEnum):
    AUTO = "AUTO"
    GENTLE = "GENTLE"
    PLAYFUL = "PLAYFUL"
    PRECISE = "PRECISE"
    SOCRATIC = "SOCRATIC"


class VoicePreference(enum.StrEnum):
    DISABLED = "DISABLED"
    INPUT_ONLY = "INPUT_ONLY"
    OUTPUT_ONLY = "OUTPUT_ONLY"
    INPUT_AND_OUTPUT = "INPUT_AND_OUTPUT"


class User(Base):
    __tablename__ = "identity_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    profile: Mapped[LearnerProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("role IN ('student', 'admin')", name="ck_identity_users_role"),
        CheckConstraint(
            "username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'",
            name="ck_identity_users_username",
        ),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()

    __table_args__ = (
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_auth_sessions_token_hash_sha256",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_auth_sessions_expiry_after_creation",
        ),
    )


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), primary_key=True
    )
    stage: Mapped[str | None] = mapped_column(String(32))
    grade: Mapped[int | None] = mapped_column(Integer)
    nickname: Mapped[str | None] = mapped_column(String(24))
    avatar_sha256: Mapped[str | None] = mapped_column(String(64))
    preferred_style: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PreferredStyle.AUTO.value
    )
    teacher_style: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TeacherStyle.AUTO.value
    )
    companion_pet_id: Mapped[str] = mapped_column(String(32), nullable=False, default="shuangling")
    interests: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    proactive_guidance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    voice_preference: Mapped[str] = mapped_column(
        String(32), nullable=False, default=VoicePreference.DISABLED.value
    )
    auto_read_replies: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="profile")

    __table_args__ = (
        CheckConstraint(
            "stage IS NULL OR stage IN ('PRIMARY_LOWER', 'PRIMARY_UPPER', 'JUNIOR', 'SENIOR')",
            name="ck_learner_profiles_stage",
        ),
        CheckConstraint(
            "grade IS NULL OR (grade BETWEEN 1 AND 12)", name="ck_learner_profiles_grade"
        ),
        CheckConstraint(
            "grade IS NULL OR stage IS NOT NULL",
            name="ck_learner_profiles_grade_requires_stage",
        ),
        CheckConstraint("revision >= 0", name="ck_learner_profiles_revision"),
        CheckConstraint(
            "nickname IS NULL OR char_length(nickname) BETWEEN 1 AND 24",
            name="ck_learner_profiles_nickname",
        ),
        CheckConstraint(
            "avatar_sha256 IS NULL OR avatar_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_learner_profiles_avatar_sha256",
        ),
        CheckConstraint(
            "preferred_style IN ('AUTO', 'EXAMPLE', 'VISUAL', 'STORY', 'STEP_BY_STEP', 'CODE')",
            name="ck_learner_profiles_preferred_style",
        ),
        CheckConstraint(
            "teacher_style IN ('AUTO', 'GENTLE', 'PLAYFUL', 'PRECISE', 'SOCRATIC')",
            name="ck_learner_profiles_teacher_style",
        ),
        CheckConstraint(
            "companion_pet_id IN ('shuangling', 'anya', 'doraemon', "
            "'kun-like', 'lulu-capybara', 'shinchan')",
            name="ck_learner_profiles_companion_pet_id",
        ),
        CheckConstraint(
            "voice_preference IN ('DISABLED', 'INPUT_ONLY', 'OUTPUT_ONLY', 'INPUT_AND_OUTPUT')",
            name="ck_learner_profiles_voice_preference",
        ),
        CheckConstraint(
            "jsonb_typeof(interests) = 'array'",
            name="ck_learner_profiles_interests_array",
        ),
    )


class ProfileAvatar(Base):
    """Private, normalized avatar bytes; reads are scoped to the signed-in user."""

    __tablename__ = "identity_profile_avatars"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity_users.id", ondelete="CASCADE"), primary_key=True
    )
    image_png: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "octet_length(image_png) BETWEEN 1 AND 1048576", name="ck_profile_avatar_image_size"
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_profile_avatar_sha256"),
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        CheckConstraint(
            "username_hash ~ '^[0-9a-f]{64}$'",
            name="ck_login_attempts_username_hash_sha256",
        ),
    )
