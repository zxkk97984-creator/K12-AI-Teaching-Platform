"""Student-owned avatar normalization and persistence."""

from __future__ import annotations

import hashlib
import io
import uuid
import warnings
from datetime import UTC, datetime

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import LearnerProfile, ProfileAvatar
from app.modules.identity.service import ProfileNotReady

MAX_AVATAR_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_AVATAR_IMAGE_BYTES = 1024 * 1024
AVATAR_SIZE = (256, 256)
INPUT_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}


class AvatarInvalid(ValueError):
    pass


def normalize_avatar(raw: bytes, media_type: str) -> tuple[bytes, str]:
    """Decode and re-encode a bounded square PNG, discarding source metadata."""

    if media_type not in INPUT_FORMATS:
        raise AvatarInvalid("仅支持 PNG、JPG 或 WebP 图片")
    if not raw or len(raw) > MAX_AVATAR_UPLOAD_BYTES:
        raise AvatarInvalid("头像文件必须小于 2 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format != INPUT_FORMATS[media_type]:
                    raise AvatarInvalid("图片格式与文件类型不一致")
                if (
                    min(source.size) < 32
                    or max(source.size) > 4096
                    or source.width * source.height > 16_000_000
                ):
                    raise AvatarInvalid("图片边长需要在 32–4096 像素之间")
                source.seek(0)
                oriented = ImageOps.exif_transpose(source)
                square = ImageOps.fit(
                    oriented.convert("RGBA"), AVATAR_SIZE, method=Image.Resampling.LANCZOS
                )
                output = io.BytesIO()
                square.save(output, format="PNG", optimize=True)
                content = output.getvalue()
    except AvatarInvalid:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as caught:
        raise AvatarInvalid("图片无法读取或已损坏") from caught
    if len(content) > MAX_AVATAR_IMAGE_BYTES:
        raise AvatarInvalid("图片处理后超过头像大小限制")
    return content, hashlib.sha256(content).hexdigest()


async def save_avatar(
    db: AsyncSession, *, owner_user_id: uuid.UUID, image_png: bytes, sha256: str
) -> LearnerProfile:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == owner_user_id).with_for_update()
    )
    if profile is None:
        raise ProfileNotReady("profile missing")
    existing = await db.get(ProfileAvatar, owner_user_id)
    if existing is not None and existing.sha256 == sha256 and profile.avatar_sha256 == sha256:
        return profile
    if existing is None:
        db.add(ProfileAvatar(owner_user_id=owner_user_id, image_png=image_png, sha256=sha256))
    else:
        existing.image_png = image_png
        existing.sha256 = sha256
        existing.updated_at = datetime.now(UTC)
    profile.avatar_sha256 = sha256
    profile.revision += 1
    profile.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(profile)
    return profile


async def remove_avatar(db: AsyncSession, *, owner_user_id: uuid.UUID) -> LearnerProfile:
    profile = await db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == owner_user_id).with_for_update()
    )
    if profile is None:
        raise ProfileNotReady("profile missing")
    existing = await db.get(ProfileAvatar, owner_user_id)
    if existing is None and profile.avatar_sha256 is None:
        return profile
    if existing is not None:
        await db.delete(existing)
    profile.avatar_sha256 = None
    profile.revision += 1
    profile.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_avatar(db: AsyncSession, *, owner_user_id: uuid.UUID) -> ProfileAvatar | None:
    return await db.get(ProfileAvatar, owner_user_id)
