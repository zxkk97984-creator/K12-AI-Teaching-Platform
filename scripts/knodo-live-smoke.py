#!/home/zxk/Projects/K12/backend/.venv/bin/python
"""Run the bounded T11 synthetic Knodo smoke sequence.

The command makes at most three Bot Chat requests, never retries, and records
only redacted metadata. The PAT is read exclusively from ``KNODO_PAT`` and is
never printed or written. Workspace history is intentionally not queried:
an administrator-created PAT should not receive that broader capability merely
for smoke-test evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import getpass
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    if not isinstance(actual, str):
        return False
    actual_label = _normalized_label(actual)
    expected_label = _normalized_label(expected)
    return actual_label in {expected_label, f"knodo{expected_label}"}


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
        gateway_timeout_seconds=120,
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


async def _run_live(
    config: dict[str, Any], *, resume_valid_first: bool = False, designer_only: bool = False
) -> int:
    from app.integrations.knodo import GatewayStatus, Operation, build_gateway

    gateway = build_gateway(_settings(config))
    records: list[dict[str, Any]] = []
    sequence_complete = False
    try:
        first = _load_json(EXAMPLES / "teaching-request.json")
        first["request_id"] = "synthetic-t11-live-tutor-first"
        if designer_only:
            prior = _load_json(EVIDENCE_PATH)
            prior_records = prior.get("records")
            records = (
                [
                    dict(item)
                    for item in prior_records
                    if isinstance(item, dict)
                    and item.get("operation") == "TEACH_TURN"
                    and item.get("status") == "OK"
                ]
                if isinstance(prior_records, list)
                else []
            )
            if len(records) < 2:
                print(
                    "Two valid Tutor records are required before Designer-only mode.",
                    file=sys.stderr,
                )
                return 2
            conversation_id = None
        elif resume_valid_first:
            prior = _load_json(EVIDENCE_PATH)
            prior_records = prior.get("records")
            if (
                not isinstance(prior_records, list)
                or not prior_records
                or not isinstance(prior_records[0], dict)
                or prior_records[0].get("status") != "OK"
                or not isinstance(prior_records[0].get("remote_metadata"), dict)
            ):
                print("No valid first-turn evidence to resume.", file=sys.stderr)
                return 2
            records = [dict(prior_records[0])]
            records[0].pop("configuration_mismatch", None)
            records[0]["model_match"] = "KNODO_PROVIDER_PREFIX_ACCEPTED"
            conversation_id = records[0]["remote_metadata"].get("conversation_id")
        else:
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
        if not designer_only:
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
        sequence_complete = True
        return _write_evidence(config, records, sequence_complete)
    finally:
        await gateway.aclose()


def _write_evidence(
    config: dict[str, Any], records: list[dict[str, Any]], sequence_complete: bool
) -> int:
    prior_failed_records: list[dict[str, Any]] = []
    if EVIDENCE_PATH.is_file():
        existing = _load_json(EVIDENCE_PATH)
        existing_failed = existing.get("prior_failed_records")
        if isinstance(existing_failed, list):
            prior_failed_records.extend(item for item in existing_failed if isinstance(item, dict))
        existing_records = existing.get("records")
        if isinstance(existing_records, list):
            prior_failed_records.extend(
                item
                for item in existing_records
                if isinstance(item, dict) and item.get("status") != "OK"
            )
    evidence = {
        "schema_version": "k12.knodo.live-smoke.redacted.v1",
        "executed_at": datetime.now(UTC).isoformat(),
        "data_class": "SYNTHETIC_ONLY",
        "automatic_retries": 0,
        "approved_request_cap": config["live_authorization"]["max_actual_requests"],
        "requests_reserved_this_run": sum(item["upstream_calls"] for item in records),
        "sequence_complete": sequence_complete,
        "records": records,
        "prior_failed_records": prior_failed_records,
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
        help="send the three-request synthetic smoke sequence (never retries)",
    )
    parser.add_argument(
        "--prompt-pat",
        action="store_true",
        help="read KNODO_PAT once from a hidden terminal prompt; never persist it",
    )
    parser.add_argument(
        "--resume-valid-first",
        action="store_true",
        help="reuse the valid first Tutor result in the redacted evidence file",
    )
    parser.add_argument(
        "--designer-only",
        action="store_true",
        help="reuse two valid Tutor records and run only Designer",
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
                    "planned_max_requests": 3,
                    "authorised_total_cap": config["live_authorization"]["max_actual_requests"],
                    "automatic_retries": 0,
                    "config": str(CONFIG_PATH),
                    "ledger": os.environ.get("KNODO_BUDGET_LEDGER_PATH", str(DEFAULT_LEDGER)),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if not token_present and args.prompt_pat:
        token = getpass.getpass("Knodo PAT（隐藏输入，不会保存）: ")
        if token:
            os.environ["KNODO_PAT"] = token
            token_present = True
        token = ""
    if not token_present:
        print(
            "KNODO_PAT is not visible; use --prompt-pat or inject the variable. No request sent.",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(
        _run_live(
            config,
            resume_valid_first=args.resume_valid_first,
            designer_only=args.designer_only,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
