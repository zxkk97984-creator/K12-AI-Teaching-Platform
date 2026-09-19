"""Restricted local filesystem store: symlink-safe, size-bounded, atomic."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.storage.keys import StorageKeyError, validate_storage_key

CHUNK = 1024 * 1024
TEMP_PREFIX = ".upload-"


class StorageError(Exception):
    """Filesystem-level failure that must surface as a readable API error."""


@dataclass(frozen=True)
class StorageWriteResult:
    key: str
    size_bytes: int
    sha256: str


class LocalFileStore:
    """All reads/writes go through the root; nothing escapes it."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    # -- path resolution -------------------------------------------------
    def _ensure_root(self) -> Path:
        root = self.root
        root.mkdir(parents=True, exist_ok=True)
        resolved = root.resolve(strict=True)
        if root.is_symlink():
            raise StorageError("STORAGE_ROOT_SYMLINK")
        return resolved

    def resolve(self, key: str) -> Path:
        """Validate ``key`` and prove the result stays inside the root."""

        relative = validate_storage_key(key)
        root = self._ensure_root()
        candidate = root
        for part in relative.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise StorageError("STORAGE_PATH_SYMLINK")
        resolved = candidate.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise StorageError("STORAGE_PATH_ESCAPES_ROOT")
        return candidate

    # -- writes ----------------------------------------------------------
    def write_stream(self, key: str, stream: BinaryIO, *, max_bytes: int) -> StorageWriteResult:
        """Stream to a temp file, enforcing ``max_bytes``; atomically publish."""

        target = self.resolve(key)
        root = self._ensure_root()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise StorageError("STORAGE_PATH_SYMLINK")
        temp = root / f"{TEMP_PREFIX}{uuid.uuid4().hex}"
        digest = hashlib.sha256()
        total = 0
        try:
            with temp.open("wb") as sink:
                while True:
                    block = stream.read(CHUNK)
                    if not block:
                        break
                    total += len(block)
                    if total > max_bytes:
                        raise StorageError("STORAGE_TOO_LARGE")
                    digest.update(block)
                    sink.write(block)
            if total == 0:
                raise StorageError("STORAGE_EMPTY_UPLOAD")
            os.replace(temp, target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return StorageWriteResult(key=key, size_bytes=total, sha256=digest.hexdigest())

    def write_temp(self, stream: BinaryIO, *, max_bytes: int) -> tuple[Path, int, str]:
        """Stage bytes for sniffing before a key is chosen."""

        root = self._ensure_root()
        temp = root / f"{TEMP_PREFIX}{uuid.uuid4().hex}"
        digest = hashlib.sha256()
        total = 0
        try:
            with temp.open("wb") as sink:
                while True:
                    block = stream.read(CHUNK)
                    if not block:
                        break
                    total += len(block)
                    if total > max_bytes:
                        raise StorageError("STORAGE_TOO_LARGE")
                    digest.update(block)
                    sink.write(block)
            if total == 0:
                raise StorageError("STORAGE_EMPTY_UPLOAD")
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return temp, total, digest.hexdigest()

    async def write_temp_stream(
        self, chunks: AsyncIterator[bytes], *, max_bytes: int
    ) -> tuple[Path, int, str]:
        """Async twin of :meth:`write_temp` for raw request bodies."""

        root = self._ensure_root()
        temp = root / f"{TEMP_PREFIX}{uuid.uuid4().hex}"
        digest = hashlib.sha256()
        total = 0
        try:
            with temp.open("wb") as sink:
                async for block in chunks:
                    if not isinstance(block, (bytes, bytearray)):  # pragma: no cover
                        raise StorageError("STORAGE_BLOCK_INVALID")
                    total += len(block)
                    if total > max_bytes:
                        raise StorageError("STORAGE_TOO_LARGE")
                    digest.update(block)
                    sink.write(block)
            if total == 0:
                raise StorageError("STORAGE_EMPTY_UPLOAD")
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return temp, total, digest.hexdigest()

    def publish_temp(self, temp: Path, key: str) -> Path:
        target = self.resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise StorageError("STORAGE_PATH_SYMLINK")
        os.replace(temp, target)
        return target

    # -- reads -----------------------------------------------------------
    def exists(self, key: str) -> bool:
        try:
            return self.resolve(key).is_file()
        except StorageError:
            return False

    def size(self, key: str) -> int:
        path = self.resolve(key)
        if not path.is_file():
            raise StorageError("STORAGE_FILE_MISSING")
        return path.stat().st_size

    def open(self, key: str) -> BinaryIO:
        path = self.resolve(key)
        if not path.is_file():
            raise StorageError("STORAGE_FILE_MISSING")
        return path.open("rb")

    def iter_chunks(self, key: str) -> Iterator[bytes]:
        with self.open(key) as stream:
            while True:
                block = stream.read(CHUNK)
                if not block:
                    break
                yield block

    def cleanup_temp(self, temp: Path) -> None:
        try:
            temp.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best effort only
            pass

    def purge_orphan_temp(self) -> int:
        root = self._ensure_root()
        removed = 0
        for entry in root.glob(f"{TEMP_PREFIX}*"):
            if entry.is_file():
                entry.unlink(missing_ok=True)
                removed += 1
        return removed

    def disk_usage_bytes(self) -> int:  # pragma: no cover - diagnostics only
        root = self._ensure_root()
        total = 0
        for dirpath, _dirs, files in os.walk(root, followlinks=False):
            for name in files:
                path = Path(dirpath) / name
                if path.is_symlink():
                    continue
                total += path.stat().st_size
        return total

    def remove(self, key: str) -> None:
        path = self.resolve(key)
        if path.is_file():
            path.unlink()
        parent = path.parent
        root = self._ensure_root()
        while parent != root and parent.is_dir():
            try:
                next(parent.iterdir())
            except StopIteration:
                shutil.rmtree(parent, ignore_errors=True)
                parent = parent.parent
                continue
            break


__all__ = ["CHUNK", "LocalFileStore", "StorageError", "StorageKeyError", "StorageWriteResult"]
