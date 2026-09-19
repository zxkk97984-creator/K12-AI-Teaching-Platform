from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings


@dataclass(frozen=True)
class PasswordHasherConfig:
    time_cost: int
    memory_cost: int
    parallelism: int


class PasswordManager:
    def __init__(self, settings: Settings):
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
        )

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True


# A syntactically valid Argon2 hash used only to keep missing-user timing comparable.
_DUMMY_HASH = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("dummy-password")


def verify_dummy_password(manager: PasswordManager, password: str) -> None:
    manager.verify(_DUMMY_HASH, password)


def normalize_username(value: str) -> str:
    return value.strip().lower()


def username_fingerprint(secret: str, username: str) -> str:
    normalized = normalize_username(username)
    return hmac.new(secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equal(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left, right)
