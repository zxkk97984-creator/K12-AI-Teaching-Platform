#!/usr/bin/env python3
"""Export the content/catalogue HTTP contract (T08)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.modules.identity.openapi import prune_schema

CONTENT_PATH_PREFIXES = (
    "/api/v1/courses",
    "/api/v1/chapters",
    "/api/v1/content/",
    "/api/v1/reading-events",
)


def is_content_path(path: str) -> bool:
    return path.startswith(CONTENT_PATH_PREFIXES)


def export_content_schema() -> dict:
    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        app_env="test",
        app_session_secret="openapi-export-secret-not-a-production-value",
        test_database_url="postgresql+asyncpg://unused:unused@127.0.0.1:55434/openapi_test",
        allowed_origins="http://127.0.0.1:15173",
        cookie_secure=False,
    )
    return prune_schema(create_app(settings).openapi(), is_content_path)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.modules.content.openapi OUTPUT")
    output = Path(sys.argv[1]).resolve()
    schema = export_content_schema()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
