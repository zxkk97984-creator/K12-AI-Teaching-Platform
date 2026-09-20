#!/home/zxk/Projects/K12/backend/.venv/bin/python
"""Inspect one completed Designer conversation without invoking the model."""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
CONFIG = ROOT / "docs/integrations/knodo/tenant-config.user-reported.json"
EVIDENCE = ROOT / "docs/integrations/knodo/live-smoke.redacted.json"
OUTPUT = ROOT / "docs/integrations/knodo/designer-inspection.redacted.json"
LEDGER = ROOT / "storage/private/knodo-request-budget.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("expected object")
    return value


async def run(token: str) -> int:
    from app.integrations.knodo.budget import FileRequestBudget
    from app.integrations.knodo.operations import Operation
    from app.integrations.knodo.schema_models import default_registry

    config = _load(CONFIG)
    evidence = _load(EVIDENCE)
    records = evidence.get("records")
    record = (
        next(
            (
                item
                for item in records
                if isinstance(item, dict) and item.get("operation") == "QUIZ_DRAFT"
            ),
            None,
        )
        if isinstance(records, list)
        else None
    )
    metadata = record.get("remote_metadata") if isinstance(record, dict) else None
    conversation_id = metadata.get("conversation_id") if isinstance(metadata, dict) else None
    if not isinstance(conversation_id, str) or not conversation_id:
        print("No completed Designer conversation in evidence.", file=sys.stderr)
        return 2

    budget = FileRequestBudget(
        os.environ.get("KNODO_BUDGET_LEDGER_PATH", str(LEDGER)),
        max_requests=config["live_authorization"]["max_actual_requests"],
    )
    result: dict[str, Any] = {
        "schema_version": "k12.knodo.designer-inspection.redacted.v1",
        "checked_at": datetime.now(UTC).isoformat(),
        "request_id": record.get("request_id"),
        "conversation_id": conversation_id,
        "requests_reserved": 0,
        "outcome": "UNRESOLVED",
    }
    if not await budget.reserve():
        result["reason_code"] = "LIVE_REQUEST_BUDGET_EXHAUSTED"
        _save(result)
        return 1
    result["requests_reserved"] = 1
    target = config["targets"]["designer"]
    url = (
        f"{config['platform_origin']}/api/v1/workspaces/{target['workspace_id']}"
        f"/chat/conversations/{quote(conversation_id, safe='')}/messages"
    )
    try:
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
            response = await client.get(
                url,
                params={"limit": 20},
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )
    except httpx.HTTPError:
        result["reason_code"] = "CONNECTION_ERROR"
        _save(result)
        return 1
    result["http_status"] = response.status_code
    if not 200 <= response.status_code < 300 or len(response.content) > 262_144:
        result["reason_code"] = (
            f"HTTP_{response.status_code}"
            if not 200 <= response.status_code < 300
            else "OUTPUT_TOO_LARGE"
        )
        _save(result)
        return 1
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        result["reason_code"] = "MALFORMED_JSON"
        _save(result)
        return 1
    data = payload.get("data") if isinstance(payload, dict) else None
    payload = data if isinstance(data, dict) else payload
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        result["reason_code"] = "SHAPE_INVALID"
        _save(result)
        return 1
    result["message_count"] = len(messages)
    content = next(
        (
            item.get("content")
            for item in messages
            if isinstance(item, dict)
            and item.get("role") == "assistant"
            and isinstance(item.get("content"), str)
        ),
        None,
    )
    if not isinstance(content, str):
        result["reason_code"] = "ASSISTANT_NOT_FOUND"
        _save(result)
        return 1
    result["assistant_content_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    try:
        semantic = json.loads(content)
    except json.JSONDecodeError:
        semantic = None
    if not isinstance(semantic, dict):
        result["reason_code"] = "ASSISTANT_CONTENT_NOT_JSON_OBJECT"
        _save(result)
        return 1
    problems = default_registry().validate_response(Operation.QUIZ_DRAFT, semantic)
    result["schema_valid"] = not problems
    result["schema_problems"] = problems
    result["outcome"] = "VALID" if not problems else "INVALID"
    if problems:
        result["reason_code"] = "RESPONSE_SCHEMA_MISMATCH"
    _save(result)
    return 0 if not problems else 1


def _save(result: dict[str, Any]) -> None:
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    token = os.environ.get("KNODO_PAT", "") or getpass.getpass("Knodo PAT（隐藏输入，不会保存）: ")
    try:
        return asyncio.run(run(token))
    finally:
        token = ""


if __name__ == "__main__":
    raise SystemExit(main())
