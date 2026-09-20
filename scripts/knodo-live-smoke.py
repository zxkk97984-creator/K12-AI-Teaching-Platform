#!/home/zxk/Projects/K12/backend/.venv/bin/python
"""Run the bounded T11 synthetic Knodo smoke sequence.

The command makes at most five requests (three Bot calls and two workspace
binding checks), never retries, and records only redacted metadata. The PAT is
read exclusively from ``KNODO_PAT`` and is never printed or written.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
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
EXAMPLES = ROOT / "contracts/examples"
DEFAULT_LEDGER = ROOT / "storage/private/knodo-request-budget.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalized_label(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _matches_display(actual: Any, expected: str) -> bool:
    return isinstance(actual, str) and _normalized_label(actual) == _normalized_label(expected)


def _settings(config: dict[str, Any]) -> Any:
    from app.config import Settings

    targets = config["targets"]
    return Settings(
        app_env="development",
        app_session_secret="synthetic-live-smoke-session-secret-only",
        allowed_origins="http://127.0.0.1:15173",
        gateway_mode="knodo",
        knodo_base_url=config["platform_origin"],
        knodo_tutor_bot_id=targets["tutor"]["bot_id"],
        knodo_tutor_workspace_id=targets["tutor"]["workspace_id"],
        knodo_designer_bot_id=targets["designer"]["bot_id"],
        knodo_designer_workspace_id=targets["designer"]["workspace_id"],
        knodo_max_requests=config["live_authorization"]["max_actual_requests"],
        knodo_budget_ledger_path=os.environ.get("KNODO_BUDGET_LEDGER_PATH", str(DEFAULT_LEDGER)),
        gateway_timeout_seconds=20,
        gateway_max_output_bytes=262_144,
    )


def _result_record(operation: Any, request: dict[str, Any], result: Any) -> dict[str, Any]:
    error = None
    if result.error is not None:
        error = {
            "category": result.error.category.value,
            "reason_code": result.error.reason_code,
            "upstream_status": result.error.upstream_status,
        }
    return {
        "kind": "BOT_CHAT",
        "operation": operation.value,
        "request_id": request.get("request_id"),
        "request_schema_version": request.get("schema_version"),
        "request_top_level_fields": sorted(request),
        "request_sha256": _sha256(request),
        "status": result.status.value,
        "error": error,
        "remote_metadata": result.remote_metadata,
        "usage": result.usage.model_dump(mode="json"),
        "output_sha256": _sha256(result.output) if result.output is not None else None,
        "upstream_calls": result.usage.upstream_calls,
    }


async def _verify_workspace_conversation(
    config: dict[str, Any],
    *,
    role: str,
    conversation_id: str,
) -> tuple[bool, dict[str, Any]]:
    from app.integrations.knodo.budget import FileRequestBudget

    target = config["targets"][role]
    ledger = os.environ.get("KNODO_BUDGET_LEDGER_PATH", str(DEFAULT_LEDGER))
    budget = FileRequestBudget(
        ledger,
        max_requests=config["live_authorization"]["max_actual_requests"],
    )
    record: dict[str, Any] = {
        "kind": "WORKSPACE_CONVERSATION_CHECK",
        "role": role,
        "workspace_id": target["workspace_id"],
        "bot_id": target["bot_id"],
        "conversation_id": conversation_id,
        "upstream_calls": 0,
        "status": "FAILED",
        "reason_code": None,
    }
    if not await budget.reserve():
        record["reason_code"] = "LIVE_REQUEST_BUDGET_EXHAUSTED"
        return False, record

    record["upstream_calls"] = 1
    url = (
        f"{config['platform_origin']}/api/v1/workspaces/{target['workspace_id']}"
        f"/chat/conversations/{quote(conversation_id, safe='')}/messages?limit=20"
    )
    headers = {"Authorization": f"Bearer {os.environ['KNODO_PAT']}"}
    try:
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
            response = await client.get(url, headers=headers, timeout=20)
    except httpx.HTTPError:
        record["reason_code"] = "WORKSPACE_CHECK_CONNECTION_FAILED"
        return False, record
    record["http_status"] = response.status_code
    if not 200 <= response.status_code < 300:
        record["reason_code"] = f"WORKSPACE_CHECK_HTTP_{response.status_code}"
        return False, record
    if len(response.content) > 262_144:
        record["reason_code"] = "WORKSPACE_CHECK_OUTPUT_TOO_LARGE"
        return False, record
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        record["reason_code"] = "WORKSPACE_CHECK_MALFORMED_JSON"
        return False, record
    messages = payload.get("messages") if isinstance(payload, dict) else None
    runtime_type = payload.get("runtimeType") if isinstance(payload, dict) else None
    if not isinstance(messages, list) or not isinstance(runtime_type, str):
        record["reason_code"] = "WORKSPACE_CHECK_SHAPE_INVALID"
        return False, record
    record.update(
        {
            "status": "OK",
            "reason_code": None,
            "message_count": len(messages),
            "runtime_type": runtime_type,
            "conversation_status": payload.get("conversationStatus"),
        }
    )
    runtime_matches = _matches_display(runtime_type, target["agent_os_display"])
    record["expected_runtime_display"] = target["agent_os_display"]
    record["runtime_matches_reported_configuration"] = runtime_matches
    if not runtime_matches:
        record["status"] = "FAILED"
        record["reason_code"] = "WORKSPACE_RUNTIME_MISMATCH"
    return runtime_matches, record


async def _run_live(config: dict[str, Any]) -> int:
    from app.integrations.knodo import GatewayStatus, Operation, build_gateway

    gateway = build_gateway(_settings(config))
    records: list[dict[str, Any]] = []
    sequence_complete = False
    try:
        first = _load_json(EXAMPLES / "teaching-request.json")
        first["request_id"] = "synthetic-t11-live-tutor-first"
        first_result = await gateway.invoke(Operation.TEACH_TURN, first)
        records.append(_result_record(Operation.TEACH_TURN, first, first_result))
        if first_result.status is not GatewayStatus.OK or first_result.remote_metadata is None:
            return _write_evidence(config, records, sequence_complete)
        if not _matches_display(
            first_result.remote_metadata.get("model"),
            config["targets"]["tutor"]["model_display"],
        ):
            records[-1]["configuration_mismatch"] = "MODEL"
            return _write_evidence(config, records, sequence_complete)

        conversation_id = first_result.remote_metadata.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            return _write_evidence(config, records, sequence_complete)

        continuation = copy.deepcopy(first)
        continuation["request_id"] = "synthetic-t11-live-tutor-continue"
        continuation["base_revision"] = 1
        continuation["event"] = "ASK"
        continuation["current_phase"] = "EXPLAIN"
        continuation["student_input"] = "合成测试：请继续说明为什么一次比较不等于整个排序完成。"
        continue_result = await gateway.invoke(
            Operation.TEACH_TURN,
            continuation,
            remote_conversation_id=conversation_id,
        )
        records.append(_result_record(Operation.TEACH_TURN, continuation, continue_result))
        if continue_result.status is not GatewayStatus.OK:
            return _write_evidence(config, records, sequence_complete)

        tutor_verified, tutor_check = await _verify_workspace_conversation(
            config,
            role="tutor",
            conversation_id=conversation_id,
        )
        records.append(tutor_check)
        if not tutor_verified:
            return _write_evidence(config, records, sequence_complete)

        designer = _load_json(EXAMPLES / "designer-request.json")
        designer["request_id"] = "synthetic-t11-live-designer-first"
        designer_result = await gateway.invoke(Operation.QUIZ_DRAFT, designer)
        records.append(_result_record(Operation.QUIZ_DRAFT, designer, designer_result))
        if (
            designer_result.status is not GatewayStatus.OK
            or designer_result.remote_metadata is None
        ):
            return _write_evidence(config, records, sequence_complete)
        if not _matches_display(
            designer_result.remote_metadata.get("model"),
            config["targets"]["designer"]["model_display"],
        ):
            records[-1]["configuration_mismatch"] = "MODEL"
            return _write_evidence(config, records, sequence_complete)
        designer_conversation_id = designer_result.remote_metadata.get("conversation_id")
        if not isinstance(designer_conversation_id, str) or not designer_conversation_id:
            return _write_evidence(config, records, sequence_complete)
        designer_verified, designer_check = await _verify_workspace_conversation(
            config,
            role="designer",
            conversation_id=designer_conversation_id,
        )
        records.append(designer_check)
        sequence_complete = designer_verified
        return _write_evidence(config, records, sequence_complete)
    finally:
        await gateway.aclose()


def _write_evidence(
    config: dict[str, Any], records: list[dict[str, Any]], sequence_complete: bool
) -> int:
    evidence = {
        "schema_version": "k12.knodo.live-smoke.redacted.v1",
        "executed_at": datetime.now(UTC).isoformat(),
        "data_class": "SYNTHETIC_ONLY",
        "automatic_retries": 0,
        "approved_request_cap": config["live_authorization"]["max_actual_requests"],
        "requests_reserved_this_run": sum(item["upstream_calls"] for item in records),
        "sequence_complete": sequence_complete,
        "records": records,
        "secrets_recorded": False,
    }
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "sequence_complete": sequence_complete,
                "records": len(records),
                "evidence": str(EVIDENCE_PATH),
            },
            ensure_ascii=False,
        )
    )
    return 0 if sequence_complete else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="send the five-request synthetic smoke sequence (never retries)",
    )
    args = parser.parse_args()
    config = _load_json(CONFIG_PATH)
    token_present = bool(os.environ.get("KNODO_PAT"))
    if not args.live:
        print(
            json.dumps(
                {
                    "mode": "DRY_RUN",
                    "token_present": token_present,
                    "planned_max_requests": 5,
                    "authorised_total_cap": config["live_authorization"]["max_actual_requests"],
                    "automatic_retries": 0,
                    "config": str(CONFIG_PATH),
                    "ledger": os.environ.get("KNODO_BUDGET_LEDGER_PATH", str(DEFAULT_LEDGER)),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if not token_present:
        print(
            "KNODO_PAT is not visible to this process; no request was sent.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_run_live(config))


if __name__ == "__main__":
    raise SystemExit(main())
