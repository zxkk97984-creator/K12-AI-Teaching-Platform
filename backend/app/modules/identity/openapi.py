#!/usr/bin/env python3
"""Export the frozen identity/health HTTP contract.

The application schema now also contains content endpoints. This exporter
therefore filters the live app schema down to the identity and health paths and
prunes component schemas that are no longer referenced, so
``contracts/openapi.identity.json`` keeps its exact byte representation while
``contracts/openapi.content.json`` is produced by the content exporter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.config import Settings
from app.main import create_app

HEALTH_PATHS = ("/health/live", "/health/ready")
IDENTITY_PATH_PREFIXES = ("/api/v1/auth/", "/api/v1/me", "/api/v1/admin/identity/")
REF_PREFIX = "#/components/schemas/"


def is_identity_path(path: str) -> bool:
    return path in HEALTH_PATHS or path.startswith(IDENTITY_PATH_PREFIXES)


def _collect_refs(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(REF_PREFIX):
                found.add(value[len(REF_PREFIX) :])
            else:
                _collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, found)


def prune_schema(schema: dict[str, Any], keep_path) -> dict[str, Any]:
    """Keep selected paths plus the component schemas they reach transitively."""

    paths = {path: item for path, item in schema.get("paths", {}).items() if keep_path(path)}
    all_schemas: dict[str, Any] = schema.get("components", {}).get("schemas", {})
    referenced: set[str] = set()
    _collect_refs(paths, referenced)
    pending = list(referenced)
    while pending:
        name = pending.pop()
        node = all_schemas.get(name)
        if node is None:
            continue
        discovered: set[str] = set()
        _collect_refs(node, discovered)
        for candidate in discovered - referenced:
            referenced.add(candidate)
            pending.append(candidate)

    filtered = dict(schema)
    filtered["paths"] = paths
    if "components" in filtered:
        components = dict(filtered["components"])
        if "schemas" in components:
            components["schemas"] = {
                name: body for name, body in all_schemas.items() if name in referenced
            }
        filtered["components"] = components
    return filtered


def export_identity_schema() -> dict[str, Any]:
    settings = Settings(
        app_env="test",
        app_session_secret="openapi-export-secret-not-a-production-value",
        test_database_url="postgresql+asyncpg://unused:unused@127.0.0.1:55434/openapi_test",
        allowed_origins="http://127.0.0.1:15173",
        cookie_secure=False,
    )
    return prune_schema(create_app(settings).openapi(), is_identity_path)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.modules.identity.openapi OUTPUT")
    output = Path(sys.argv[1]).resolve()
    schema = export_identity_schema()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
