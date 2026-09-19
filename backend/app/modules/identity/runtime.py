"""Configuration re-exports for identity tooling; never imports the ASGI app."""

from app.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
