"""Storage key validation: the only place a key becomes a filesystem path."""

from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath

MAX_KEY_LENGTH = 400
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class StorageKeyError(ValueError):
    """A key that must never reach the filesystem."""


def validate_storage_key(key: str) -> PurePosixPath:
    """Return a validated relative POSIX path, or raise ``StorageKeyError``.

    Rejects absolute paths, traversal, backslashes, NUL, empty/hidden segments
    and any segment with characters outside the storage alphabet.
    """

    if not isinstance(key, str) or not key:
        raise StorageKeyError("STORAGE_KEY_EMPTY")
    if len(key) > MAX_KEY_LENGTH:
        raise StorageKeyError("STORAGE_KEY_TOO_LONG")
    if "\x00" in key:
        raise StorageKeyError("STORAGE_KEY_NUL")
    if "\\" in key:
        raise StorageKeyError("STORAGE_KEY_BACKSLASH")
    if key.startswith("/") or key.startswith("~"):
        raise StorageKeyError("STORAGE_KEY_ABSOLUTE")
    if re.match(r"^[A-Za-z]:", key):
        raise StorageKeyError("STORAGE_KEY_DRIVE")
    relative = PurePosixPath(key)
    if relative.is_absolute() or len(relative.parts) < 2:
        raise StorageKeyError("STORAGE_KEY_NOT_RELATIVE")
    for part in relative.parts:
        if part in {".", ".."}:
            raise StorageKeyError("STORAGE_KEY_TRAVERSAL")
        if not _SEGMENT_RE.match(part):
            raise StorageKeyError("STORAGE_KEY_SEGMENT_INVALID")
    return relative


def build_storage_key(*, resource_id: uuid.UUID, variant: str, extension: str) -> str:
    """Server-generated key. Clients never supply a key."""

    if variant not in {"SOURCE", "PREVIEW"}:
        raise StorageKeyError("STORAGE_VARIANT_INVALID")
    suffix = extension.lower()
    if not suffix.startswith(".") or not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        raise StorageKeyError("STORAGE_EXTENSION_INVALID")
    key = f"resources/{resource_id}/{variant.lower()}-{uuid.uuid4().hex}{suffix}"
    validate_storage_key(key)
    return key
