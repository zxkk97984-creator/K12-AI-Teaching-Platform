from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.identity.models import (
    AuthSession,
    LearnerProfile,
    LoginAttempt,
    PreferredStyle,
    User,
    UserRole,
    VoicePreference,
)
from app.modules.identity.schemas import PreferencesPatch, ProfilePatch
from app.modules.identity.security import (
    PasswordManager,
    hash_session_token,
    new_session_token,
    normalize_username,
    username_fingerprint,
    verify_dummy_password,
)


class IdentityError(Exception):
    pass


class InvalidCredentials(IdentityError):
    pass


class LoginRateLimited(IdentityError):
    pass


class ProfileNotReady(IdentityError):
    pass


class RevisionConflict(IdentityError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    role: UserRole,
    stage: str | None = None,
    grade: int | None = None,
    preferred_style: PreferredStyle | str = PreferredStyle.AUTO,
    interests: list[str] | None = None,
    proactive_guidance_enabled: bool = True,
    voice_preference: VoicePreference | str = VoicePreference.DISABLED,
    settings: Settings,
) -> User:
    normalized = normalize_username(username)
    existing = await db.scalar(select(User).where(User.username == normalized))
    if existing:
        return existing
    user = User(
        id=uuid.uuid4(),
        username=normalized,
        password_hash=PasswordManager(settings).hash(password),
        role=role.value,
        is_active=True,
    )
    db.add(user)
    if role == UserRole.STUDENT:
        db.add(
            LearnerProfile(
                user_id=user.id,
                stage=stage,
                grade=grade,
                preferred_style=(
                    preferred_style.value
                    if isinstance(preferred_style, PreferredStyle)
                    else preferred_style
                ),
                interests=interests or [],
                proactive_guidance_enabled=proactive_guidance_enabled,
                voice_preference=(
                    voice_preference.value
                    if isinstance(voice_preference, VoicePreference)
                    else voice_preference
                ),
                revision=0,
            )
        )
    await db.flush()
    return user


async def ensure_demo_user(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    role: UserRole,
    stage: str | None,
    grade: int | None,
    preferred_style: PreferredStyle,
    interests: list[str],
    settings: Settings,
) -> tuple[User, bool]:
    """Idempotently create a synthetic account; never overwrite an existing account."""
    normalized = normalize_username(username)
    user = await db.scalar(select(User).where(User.username == normalized))
    if user:
        return user, False
    user = await create_user(
        db,
        username=normalized,
        password=password,
        role=role,
        stage=stage,
        grade=grade,
        preferred_style=preferred_style,
        interests=interests,
        settings=settings,
    )
    await db.commit()
    return user, True


async def is_login_rate_limited(db: AsyncSession, settings: Settings, username: str) -> bool:
    cutoff = _now() - timedelta(seconds=settings.login_rate_limit_window_seconds)
    fingerprint = username_fingerprint(settings.app_session_secret or "", username)
    count = await db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.username_hash == fingerprint,
            LoginAttempt.failed_at >= cutoff,
        )
    )
    return int(count or 0) >= settings.login_rate_limit_attempts


async def record_login_failure(db: AsyncSession, settings: Settings, username: str) -> None:
    cutoff = _now() - timedelta(seconds=settings.login_rate_limit_window_seconds)
    fingerprint = username_fingerprint(settings.app_session_secret or "", username)
    await db.execute(delete(LoginAttempt).where(LoginAttempt.failed_at < cutoff))
    db.add(LoginAttempt(username_hash=fingerprint, failed_at=_now()))
    await db.commit()


async def clear_login_failures(db: AsyncSession, settings: Settings, username: str) -> None:
    fingerprint = username_fingerprint(settings.app_session_secret or "", username)
    await db.execute(delete(LoginAttempt).where(LoginAttempt.username_hash == fingerprint))


async def authenticate(
    db: AsyncSession, settings: Settings, username: str, password: str
) -> User | None:
    normalized = normalize_username(username)
    user = await db.scalar(select(User).where(User.username == normalized))
    if user is None:
        verify_dummy_password(PasswordManager(settings), password)
        await record_login_failure(db, settings, normalized)
        return None
    if not user.is_active:
        verify_dummy_password(PasswordManager(settings), password)
        await record_login_failure(db, settings, normalized)
        return None
    if not PasswordManager(settings).verify(user.password_hash, password):
        await record_login_failure(db, settings, normalized)
        return None
    await clear_login_failures(db, settings, normalized)
    return user


async def create_auth_session(db: AsyncSession, settings: Settings, user: User) -> str:
    raw_token = new_session_token()
    now = _now()
    db.add(
        AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    await db.commit()
    return raw_token


async def revoke_auth_session(db: AsyncSession, token: str | None) -> None:
    if not token:
        return
    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.token_hash == hash_session_token(token), AuthSession.revoked_at.is_(None)
        )
        .values(revoked_at=_now())
    )
    await db.commit()


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> LearnerProfile | None:
    return await db.scalar(select(LearnerProfile).where(LearnerProfile.user_id == user_id))


def _validate_stage_grade(stage: str | None, grade: int | None) -> None:
    if grade is not None:
        if stage is None:
            raise IdentityError("grade requires stage")
        expected = (
            "PRIMARY_LOWER"
            if 1 <= grade <= 3
            else "PRIMARY_UPPER"
            if 4 <= grade <= 6
            else "JUNIOR"
            if 7 <= grade <= 9
            else "SENIOR"
            if 10 <= grade <= 12
            else None
        )
        if expected != stage:
            raise IdentityError("grade and stage disagree")


async def update_profile(
    db: AsyncSession, user_id: uuid.UUID, patch: ProfilePatch
) -> LearnerProfile:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        raise ProfileNotReady("profile missing")
    if profile.revision != patch.base_revision:
        raise RevisionConflict("profile revision mismatch")
    values = patch.model_dump(exclude={"base_revision"}, exclude_unset=True)
    next_stage = values.get("stage", profile.stage)
    next_grade = values.get("grade", profile.grade)
    _validate_stage_grade(next_stage, next_grade)
    if "stage" in values:
        profile.stage = next_stage.value if next_stage is not None else None
    if "grade" in values:
        profile.grade = next_grade
    profile.revision += 1
    profile.updated_at = _now()
    await db.commit()
    await db.refresh(profile)
    return profile


async def update_preferences(
    db: AsyncSession, user_id: uuid.UUID, patch: PreferencesPatch
) -> LearnerProfile:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == user_id).with_for_update()
    )
    if profile is None:
        raise ProfileNotReady("profile missing")
    if profile.revision != patch.base_revision:
        raise RevisionConflict("profile revision mismatch")
    values = patch.model_dump(exclude={"base_revision"}, exclude_unset=True)
    for key, value in values.items():
        if key == "preferred_style" and value is not None:
            profile.preferred_style = value.value
        elif key == "voice_preference" and value is not None:
            profile.voice_preference = value.value
        else:
            setattr(profile, key, value)
    profile.revision += 1
    profile.updated_at = _now()
    await db.commit()
    await db.refresh(profile)
    return profile


async def active_session_count(db: AsyncSession) -> int:
    count = await db.scalar(
        select(func.count(AuthSession.id)).where(
            AuthSession.revoked_at.is_(None), AuthSession.expires_at > _now()
        )
    )
    return int(count or 0)


async def active_student_count(db: AsyncSession) -> int:
    count = await db.scalar(
        select(func.count(User.id)).where(
            User.role == UserRole.STUDENT.value, User.is_active.is_(True)
        )
    )
    return int(count or 0)
