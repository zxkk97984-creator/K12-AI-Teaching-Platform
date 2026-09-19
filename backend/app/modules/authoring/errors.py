"""Authoring domain errors, shared by the material loader and the service."""

from __future__ import annotations


class AuthoringError(Exception):
    """A refused authoring operation, mapped to a readable HTTP error."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status_code = status_code


__all__ = ["AuthoringError"]
