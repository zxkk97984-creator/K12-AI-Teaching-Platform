"""Short-lived signed tickets for resource downloads.

The ticket is an HMAC over ``{resource, variant, owner, expiry}``. It is
**never** persisted: it is not a curriculum resource id, it cannot outlive its
expiry, and it is bound to the same authenticated owner that requested it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

TICKET_TTL_SECONDS = 120
SIG_LENGTH = 32


class TicketError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(secret: str, body: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256)
    return _b64(mac.digest())[:SIG_LENGTH]


def sign_ticket(
    secret: str,
    *,
    resource_id: uuid.UUID,
    variant: str,
    owner_user_id: uuid.UUID,
    ttl_seconds: int = TICKET_TTL_SECONDS,
    now: float | None = None,
) -> tuple[str, int]:
    """Return ``(token, expires_at_epoch)``. Nothing is stored server-side."""

    if variant not in {"SOURCE", "PREVIEW"}:
        raise TicketError("RESOURCE_VARIANT_INVALID", "资源变体无效")
    issued = int(now if now is not None else time.time())
    expires = issued + max(1, min(ttl_seconds, 900))
    payload = {"r": str(resource_id), "v": variant, "o": str(owner_user_id), "e": expires}
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(secret, body)}", expires


def verify_ticket(secret: str, token: str, *, now: float | None = None) -> dict[str, str]:
    if not token or "." not in token:
        raise TicketError("RESOURCE_TICKET_INVALID", "资源链接无效")
    body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(secret, body), signature):
        raise TicketError("RESOURCE_TICKET_INVALID", "资源链接无效")
    try:
        payload = json.loads(_unb64(body))
        expires = int(payload["e"])
        record = {"r": str(payload["r"]), "v": str(payload["v"]), "o": str(payload["o"])}
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise TicketError("RESOURCE_TICKET_INVALID", "资源链接无效") from None
    current = int(now if now is not None else time.time())
    if current > expires:
        raise TicketError("RESOURCE_TICKET_EXPIRED", "资源链接已过期，请重新获取")
    return record


__all__ = ["TICKET_TTL_SECONDS", "TicketError", "sign_ticket", "verify_ticket"]
