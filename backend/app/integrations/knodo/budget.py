"""Optional durable request cap for live Knodo calls."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "k12.knodo.request-budget.v1"


class UnlimitedRequestBudget:
    """Allow explicitly uncapped calls without reading or changing an old ledger."""

    async def reserve(self) -> bool:
        return True


class FileRequestBudget:
    """Reserve calls across processes and restarts before network submission.

    A reservation is deliberately never refunded: timeout, cancellation after
    submission, or a lost response may still have consumed upstream resources.
    Existing ledgers can be tightened but cannot be enlarged automatically.
    """

    def __init__(self, path: str | Path, *, max_requests: int):
        if max_requests < 1:
            raise ValueError("max_requests must be positive")
        self.path = Path(path)
        self.max_requests = max_requests

    async def reserve(self) -> bool:
        return await asyncio.to_thread(self._reserve_sync)

    def _reserve_sync(self) -> bool:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            lock_path = self.path.with_name(f".{self.path.name}.lock")
            flags = os.O_CREAT | os.O_RDWR
            flags |= getattr(os, "O_NOFOLLOW", 0)
            lock_fd = os.open(lock_path, flags, 0o600)
            try:
                os.fchmod(lock_fd, 0o600)
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                state = self._read_state()
                if state is None:
                    if self.path.exists():
                        return False
                    authorised = self.max_requests
                    reserved = 0
                else:
                    stored_authorised = state["authorized_max_requests"]
                    reserved = state["reserved_requests"]
                    # A new process/config may reduce the cap, never raise it.
                    authorised = min(stored_authorised, self.max_requests)
                    if authorised != stored_authorised:
                        self._write_state(authorised=authorised, reserved=reserved)
                if reserved >= authorised:
                    return False
                self._write_state(authorised=authorised, reserved=reserved + 1)
                return True
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    def _read_state(self) -> dict[str, int] | None:
        try:
            mode = self.path.lstat().st_mode
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(mode):
            raise ValueError("budget ledger may not be a symlink")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags)
        try:
            with os.fdopen(fd, encoding="utf-8") as handle:
                raw: Any = json.load(handle)
        except Exception:
            # fd ownership transfers to fdopen; parsing failures must remain
            # fail-closed and preserve the original file for inspection.
            raise
        if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported budget ledger")
        authorised = raw.get("authorized_max_requests")
        reserved = raw.get("reserved_requests")
        if (
            isinstance(authorised, bool)
            or not isinstance(authorised, int)
            or authorised < 1
            or isinstance(reserved, bool)
            or not isinstance(reserved, int)
            or reserved < 0
        ):
            raise ValueError("invalid budget ledger")
        return {
            "authorized_max_requests": authorised,
            "reserved_requests": reserved,
        }

    def _write_state(self, *, authorised: int, reserved: int) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "authorized_max_requests": authorised,
            "reserved_requests": reserved,
        }
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise


__all__ = ["FileRequestBudget", "UnlimitedRequestBudget", "SCHEMA_VERSION"]
