"""Redaction helpers: no PAT, cookie or upstream body leaks into output."""

from __future__ import annotations

import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"

_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\b(?:sl_session|sl_csrf|csrf_token|session|pat|token)=[^;\s,]+"),
    re.compile(r"(?i)\b(?:pat|token|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
)


def redact_text(text: object, secrets: Iterable[str] = ()) -> str:
    """Return a log-safe string; unknown objects are stringified first."""

    value = "" if text is None else str(text)
    for secret in secrets:
        if secret:
            value = value.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def redact_url(url: str) -> str:
    """Drop credentials and query strings so a base URL is safe to log."""

    safe = redact_text(url)
    if "?" in safe:
        safe = safe.split("?", 1)[0]
    return safe
