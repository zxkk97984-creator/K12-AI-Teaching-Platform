#!/home/zxk/Projects/K12/backend/.venv/bin/python
"""Reconcile one acceptance-unknown Knodo smoke request without retrying it."""

from __future__ import annotations

import argparse
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

CONFIG_PATH = ROOT / "docs/integrations/knodo/tenant-config.user-reported.json"
EVIDENCE_PATH = ROOT / "docs/integrations/knodo/live-smoke.redacted.json"
DEFAULT_LEDGER = ROOT / "storage/private/knodo-request-budget.json"
MAX_BYTES = 262_144


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def _get_json(
    client: httpx.AsyncClient,
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
) -> tuple[int | None, dict[str, Any] | None, str | None]:
    try:
        async with client.stream(
            "GET", url, headers=headers, params=params, timeout=20
        ) as response:
            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    return response.status_code, None, "OUTPUT_TOO_LARGE"
            if not 200 <= response.status_code < 300:
                return response.status_code, None, f"HTTP_{response.status_code}"
            try:
                payload = json.loads(bytes(content) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return response.status_code, None, "MALFORMED_JSON"
            if not isinstance(payload, dict):
                return response.status_code, None, "NOT_AN_OBJECT"
            return response.status_code, payload, None
    except httpx.TimeoutException:
        return None, None, "TIMEOUT"
    except httpx.HTTPError:
        return None, None, "CONNECTION_ERROR"


def _conversation_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    candidates: Any = data.get("list") if isinstance(data, dict) else payload.get("list")
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _data_object(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


async def _reserve(budget: Any) -> bool:
    return bool(await budget.reserve())


async def reconcile(token: str) -> int:
    from app.integrations.knodo.budget import FileRequestBudget
    from app.integrations.knodo.operations import Operation
    from app.integrations.knodo.schema_models import default_registry

    config = _object(CONFIG_PATH)
    evidence = _object(EVIDENCE_PATH)
    records = evidence.get("records")
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        print("No acceptance-unknown record to reconcile.", file=sys.stderr)
        return 2
    request_id = records[0].get("request_id")
    if not isinstance(request_id, str):
        print("Smoke evidence has no request id.", file=sys.stderr)
        return 2

    target = config["targets"]["tutor"]
    budget = FileRequestBudget(
        os.environ.get("KNODO_BUDGET_LEDGER_PATH", str(DEFAULT_LEDGER)),
        max_requests=config["live_authorization"]["max_actual_requests"],
    )
    result: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "request_id": request_id,
        "requests_reserved": 0,
        "outcome": "UNRESOLVED",
    }
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
        previous = evidence.get("reconciliation")
        previous_id = previous.get("conversation_id") if isinstance(previous, dict) else None
        if isinstance(previous_id, str) and previous_id:
            conversation_id = previous_id
            result["conversation_id"] = conversation_id
            result["profile_reused"] = True
            result["profile_model"] = previous.get("profile_model")
            result["profile_runtime"] = previous.get("profile_runtime")
        else:
            if not await _reserve(budget):
                result["reason_code"] = "LIVE_REQUEST_BUDGET_EXHAUSTED"
                evidence["reconciliation"] = result
                _save(evidence)
                return 1
            result["requests_reserved"] += 1
            profile_status, profile, error = await _get_json(
                client,
                url=f"{config['platform_origin']}/api/v1/profile/conversations",
                headers=headers,
                params={
                    "botId": target["bot_id"],
                    "workspaceId": target["workspace_id"],
                    "keyword": request_id,
                    "page": 1,
                    "pageSize": 20,
                },
            )
            result["profile_http_status"] = profile_status
            if error is not None or profile is None:
                result["reason_code"] = f"PROFILE_{error or 'UNKNOWN'}"
                evidence["reconciliation"] = result
                _save(evidence)
                return 1
            conversations = _conversation_list(profile)
            result["profile_match_count"] = len(conversations)
            if not conversations:
                result["outcome"] = "NOT_FOUND"
                evidence["reconciliation"] = result
                _save(evidence)
                return 1
            conversation_id = conversations[0].get("id")
            if not isinstance(conversation_id, str) or not conversation_id:
                result["reason_code"] = "PROFILE_SHAPE_INVALID"
                evidence["reconciliation"] = result
                _save(evidence)
                return 1
            result["conversation_id"] = conversation_id
            result["profile_model"] = conversations[0].get("modelId")
            result["profile_runtime"] = conversations[0].get("runtimeType")

        base = (
            f"{config['platform_origin']}/api/v1/workspaces/{target['workspace_id']}"
            f"/chat/conversations/{quote(conversation_id, safe='')}"
        )
        previous_status = (
            previous.get("conversation_status") if isinstance(previous, dict) else None
        )
        if previous_status in {"completed", "idle", "error", "interrupted"}:
            conversation_status = previous_status
            result["status_reused"] = True
        else:
            if not await _reserve(budget):
                result["reason_code"] = "LIVE_REQUEST_BUDGET_EXHAUSTED"
                evidence["reconciliation"] = result
                _save(evidence)
                return 1
            result["requests_reserved"] += 1
            status_http, status_payload, error = await _get_json(
                client, url=f"{base}/status", headers=headers
            )
            result["status_http_status"] = status_http
            if error is not None or status_payload is None:
                result["reason_code"] = f"STATUS_{error or 'UNKNOWN'}"
                evidence["reconciliation"] = result
                _save(evidence)
                return 1
            status_data = _data_object(status_payload)
            conversation_status = status_data.get("status")
        result["conversation_status"] = conversation_status
        result["outcome"] = "ACCEPTED"
        if conversation_status not in {"completed", "idle", "error", "interrupted"}:
            evidence["reconciliation"] = result
            _save(evidence)
            return 1

        if not await _reserve(budget):
            result["reason_code"] = "LIVE_REQUEST_BUDGET_EXHAUSTED"
            evidence["reconciliation"] = result
            _save(evidence)
            return 1
        result["requests_reserved"] += 1
        messages_http, messages_payload, error = await _get_json(
            client, url=f"{base}/messages", headers=headers, params={"limit": 20}
        )
        result["messages_http_status"] = messages_http
        if error is not None or messages_payload is None:
            result["reason_code"] = f"MESSAGES_{error or 'UNKNOWN'}"
            evidence["reconciliation"] = result
            _save(evidence)
            return 1
        messages = _data_object(messages_payload).get("messages")
        if not isinstance(messages, list):
            result["reason_code"] = "MESSAGES_SHAPE_INVALID"
            evidence["reconciliation"] = result
            _save(evidence)
            return 1
        result["message_count"] = len(messages)
        assistant = next(
            (
                item.get("content")
                for item in messages
                if isinstance(item, dict)
                and item.get("role") == "assistant"
                and isinstance(item.get("content"), str)
            ),
            None,
        )
        if assistant is None:
            result["reason_code"] = "ASSISTANT_MESSAGE_NOT_FOUND"
            evidence["reconciliation"] = result
            _save(evidence)
            return 1
        try:
            semantic = json.loads(assistant)
        except json.JSONDecodeError:
            semantic = None
        if not isinstance(semantic, dict):
            result["reason_code"] = "ASSISTANT_CONTENT_NOT_JSON_OBJECT"
            result["assistant_content_sha256"] = hashlib.sha256(
                assistant.encode("utf-8")
            ).hexdigest()
            evidence["reconciliation"] = result
            _save(evidence)
            return 1
        problems = default_registry().validate_response(Operation.TEACH_TURN, semantic)
        result["assistant_content_sha256"] = _hash(semantic)
        result["schema_valid"] = not problems
        result["schema_problems"] = problems
        result["outcome"] = "COMPLETED_VALID" if not problems else "COMPLETED_INVALID"
        if problems:
            result["reason_code"] = "RESPONSE_SCHEMA_MISMATCH"
        evidence["reconciliation"] = result
        _save(evidence)
        return 0 if not problems else 1


def _save(evidence: dict[str, Any]) -> None:
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-pat", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("KNODO_PAT", "")
    if not token and args.prompt_pat:
        token = getpass.getpass("Knodo PAT（隐藏输入，不会保存）: ")
    if not token:
        print("KNODO_PAT unavailable; no reconciliation request sent.", file=sys.stderr)
        return 2
    try:
        return asyncio.run(reconcile(token))
    finally:
        token = ""


if __name__ == "__main__":
    raise SystemExit(main())
