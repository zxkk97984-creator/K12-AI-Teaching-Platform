"""Export the cross-feature learning contract used by the frontend generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.modules.identity.openapi import prune_schema

LEARNING_PREFIXES = (
    "/api/v1/conversations",
    "/api/v1/agent-runs",
    "/api/v1/growth/personal-memory",
    "/api/v1/learning/",
    "/api/v1/quiz-options",
    "/api/v1/quiz-generation-jobs",
    "/api/v1/quiz-sessions",
    "/api/v1/code-tasks",
    "/api/v1/code-runs",
    "/api/v1/code-runner/status",
    "/api/v1/quiz-wrong-questions",
    "/api/v1/growth/documents",
    "/api/v1/interactive/",
)


def is_learning_path(path: str) -> bool:
    return path.startswith(LEARNING_PREFIXES)


def export_learning_schema() -> dict:
    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        app_env="test",
        app_session_secret="openapi-export-secret-not-a-production-value",
        test_database_url="postgresql+asyncpg://unused:unused@127.0.0.1:55434/openapi_test",
        allowed_origins="http://127.0.0.1:15173",
        cookie_secure=False,
    )
    return prune_schema(create_app(settings).openapi(), is_learning_path)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.modules.learning.openapi OUTPUT")
    output = Path(sys.argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(export_learning_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
