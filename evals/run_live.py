"""Run the resumable, no-retry T31 synthetic Knodo evaluation set."""

from __future__ import annotations

import argparse
import asyncio
import copy
import getpass
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

CASES_PATH = ROOT / "evals" / "teaching_cases.jsonl"
CONFIG_PATH = (
    ROOT / "docs" / "integrations" / "knodo" / "tenant-config.user-reported.json"
)
REQUEST_EXAMPLE = ROOT / "contracts" / "examples" / "teaching-request.json"
EVIDENCE_PATH = ROOT / "docs" / "acceptance" / "T31-live-results.synthetic.json"
DEFAULT_LEDGER = ROOT / "storage" / "private" / "t31-request-budget.json"
SCHEMA_VERSION = "k12.t31.live-eval.synthetic.v1"
OPERATIONAL_CAP = 16

GRADES = {
    "PRIMARY_LOWER": 2,
    "PRIMARY_UPPER": 5,
    "JUNIOR": 8,
    "SENIOR": 11,
}
STYLES = {
    "PRIMARY_LOWER": "STORY",
    "PRIMARY_UPPER": "VISUAL",
    "JUNIOR": "STEP_BY_STEP",
    "SENIOR": "CODE",
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _load_cases() -> list[dict[str, Any]]:
    cases = [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(cases) != OPERATIONAL_CAP:
        raise ValueError(f"T31 live set must contain exactly {OPERATIONAL_CAP} cases")
    return cases


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _build_request(case: dict[str, Any]) -> dict[str, Any]:
    request = copy.deepcopy(_load_json(REQUEST_EXAMPLE))
    case_id = str(case["case_id"])
    stage = str(case["stage"])
    operation = str(case["operation"])
    request.update(
        {
            "request_id": f"t31-{case_id.casefold()}",
            "lesson_session_id": f"t31-session-{case_id.casefold()}",
            "base_revision": 0,
            "curriculum_revision": "synthetic-chapter-v1",
            "policy_revision": "t31-stage-policy-v1",
            "operation": operation,
            "event": (
                "CODE_RUN_COMPLETED"
                if operation == "CODE_FEEDBACK"
                else ("ENTER" if case["category"] == "active_opening" else "ASK")
            ),
            "current_phase": (
                "PRACTICE"
                if operation == "CODE_FEEDBACK"
                else ("ORIENT" if case["category"] == "active_opening" else "EXPLAIN")
            ),
            "learner": {
                "stage": stage,
                "grade": GRADES[stage],
                "preferred_style": STYLES[stage],
            },
            "student_input": str(case["prompt"]),
            "allowed_actions": [],
            "allowed_resource_ids": [],
            "allowed_animation_ids": [],
            "allowed_code_task_ids": [],
            "allowed_phase_suggestions": [
                "ORIENT",
                "EXPLAIN",
                "CHECK",
                "PRACTICE",
                "REFLECT",
            ],
            "limits": {
                "max_quiz_questions": 0,
                "allowed_difficulties": ["EASY", "MEDIUM"],
                "max_reply_chars": 1200,
            },
        }
    )
    request["chapter"] = {
        "id": "synthetic-sort-chapter",
        "title": "合成协议评测：相邻比较",
        "objective_ids": ["synthetic-objective-compare"],
    }
    if case["source_kind"] == "NO_SOURCE":
        request["knowledge_context"] = []
    if operation == "CODE_FEEDBACK":
        request["evidence"] = [
            {
                "id": f"synthetic-code-result-{case_id.casefold()}",
                "kind": "CODE_RESULT",
                "summary": "合成可信 runner 结果：程序已运行，但确定性测试未通过。",
            }
        ]
        request["code_feedback_facts"] = {
            "run_id": f"synthetic-run-{case_id.casefold()}",
            "task_id": "synthetic-sort-code-task",
            "code_hash": hashlib.sha256(case_id.encode("utf-8")).hexdigest(),
            "code_excerpt": "for i in range(len(values)):\n    pass",
            "execution_status": "FAILED",
            "correctness_status": "FAILED",
            "stdout_excerpt": "",
            "error_excerpt": "synthetic assertion mismatch",
            "passed_cases": 1,
            "total_cases": 2,
        }
    else:
        request["evidence"] = []
        request["code_feedback_facts"] = None
    return request


def _validate_plan(
    cases: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    from app.integrations.knodo.operations import Operation
    from app.integrations.knodo.schema_models import default_registry

    registry = default_registry()
    planned: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for case in cases:
        request = _build_request(case)
        problems = registry.validate_request(Operation(case["operation"]), request)
        if problems:
            raise ValueError(f"invalid request for {case['case_id']}: {problems}")
        planned.append((case, request))
    return planned


def _settings(config: dict[str, Any], ledger: Path) -> Any:
    from app.config import Settings

    targets = config["targets"]
    return Settings(
        app_env="development",
        app_session_secret="synthetic-t31-live-eval-session-secret",
        allowed_origins="http://127.0.0.1:15173",
        gateway_mode="knodo",
        knodo_base_url=config["platform_origin"],
        knodo_tutor_bot_id=targets["tutor"]["bot_id"],
        knodo_tutor_workspace_id=targets["tutor"]["workspace_id"],
        knodo_designer_bot_id=targets["designer"]["bot_id"],
        knodo_designer_workspace_id=targets["designer"]["workspace_id"],
        knodo_max_requests=OPERATIONAL_CAP,
        knodo_budget_ledger_path=str(ledger),
        gateway_timeout_seconds=120,
        gateway_max_output_bytes=262_144,
    )


def _atomic_write(payload: dict[str, Any]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".t31-live-", dir=EVIDENCE_PATH.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, EVIDENCE_PATH)
        os.chmod(EVIDENCE_PATH, 0o600)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _new_evidence() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "data_class": "SYNTHETIC_ONLY",
        "authorization": {
            "user_stated_request_limit": "NO_LIMIT_STATED",
            "operational_cap_for_this_versioned_run": OPERATIONAL_CAP,
            "automatic_retries": 0,
            "automatic_recharge": False,
            "plan_upgrade": False,
        },
        "eval_set": "t31-local-v1",
        "started_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "sequence_complete": False,
        "records": [],
        "secrets_recorded": False,
    }


def _load_evidence() -> dict[str, Any]:
    if not EVIDENCE_PATH.is_file():
        return _new_evidence()
    evidence = _load_json(EVIDENCE_PATH)
    if evidence.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("existing T31 evidence has an unsupported schema")
    if evidence.get("eval_set") != "t31-local-v1":
        raise ValueError("existing T31 evidence belongs to another eval set")
    return evidence


def _redacted_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    redacted = dict(metadata)
    for key in ("conversation_id", "completion_id"):
        value = redacted.pop(key, None)
        if isinstance(value, str) and value:
            redacted[f"{key}_sha256"] = hashlib.sha256(
                value.encode("utf-8")
            ).hexdigest()
    return redacted


def _automated_checks(
    case: dict[str, Any], request: dict[str, Any], output: dict[str, Any] | None
) -> dict[str, bool]:
    if output is None:
        return {
            "response_present": False,
            "source_refs_allowed": False,
            "action_allowed": False,
            "no_secret_markers": True,
        }
    allowed_sources = {
        (item["source_id"], item["revision"], item["locator"])
        for item in request["knowledge_context"]
    }
    returned_sources = {
        (item["source_id"], item["revision"], item["locator"])
        for item in output.get("source_refs", [])
    }
    action = output.get("action")
    action_allowed = action is None or action.get("type") in request["allowed_actions"]
    rendered = json.dumps(output, ensure_ascii=False).casefold()
    return {
        "response_present": True,
        "source_refs_allowed": returned_sources <= allowed_sources,
        "action_allowed": action_allowed,
        "no_secret_markers": all(
            marker not in rendered for marker in ("jvs_", "sl_session", "hidden_test")
        ),
        "no_source_case_has_no_refs": (
            case["source_kind"] != "NO_SOURCE" or not returned_sources
        ),
    }


def _result_record(
    case: dict[str, Any], request: dict[str, Any], result: Any
) -> dict[str, Any]:
    error = result.error.model_dump(mode="json") if result.error is not None else None
    return {
        "case_id": case["case_id"],
        "stage": case["stage"],
        "category": case["category"],
        "operation": case["operation"],
        "source_kind": case["source_kind"],
        "expected": case["expected"],
        "request_sha256": _sha256(request),
        "state": "RECORDED",
        "recorded_at": datetime.now(UTC).isoformat(),
        "status": result.status.value,
        "error": error,
        "usage": result.usage.model_dump(mode="json"),
        "remote_metadata": _redacted_metadata(result.remote_metadata),
        "response": result.output,
        "automated_checks": _automated_checks(case, request, result.output),
        "human_review": None,
    }


async def _run_live(
    planned: list[tuple[dict[str, Any], dict[str, Any]]],
    config: dict[str, Any],
    ledger: Path,
) -> int:
    from app.integrations.knodo import build_gateway
    from app.integrations.knodo.errors import GatewayErrorCategory

    evidence = _load_evidence()
    records = evidence["records"]
    by_case = {item["case_id"]: item for item in records}
    gateway = build_gateway(_settings(config, ledger))
    stop_reason: str | None = None
    try:
        for case, request in planned:
            case_id = case["case_id"]
            request_hash = _sha256(request)
            existing = by_case.get(case_id)
            if existing is not None:
                if existing.get("request_sha256") != request_hash:
                    raise ValueError(f"request drift for recorded case {case_id}")
                if existing.get("state") == "PENDING_BEFORE_SUBMIT":
                    stop_reason = f"UPSTREAM_UNKNOWN_NO_RETRY:{case_id}"
                    break
                continue

            pending = {
                "case_id": case_id,
                "stage": case["stage"],
                "category": case["category"],
                "operation": case["operation"],
                "source_kind": case["source_kind"],
                "expected": case["expected"],
                "request_sha256": request_hash,
                "state": "PENDING_BEFORE_SUBMIT",
                "recorded_at": datetime.now(UTC).isoformat(),
                "human_review": None,
            }
            records.append(pending)
            by_case[case_id] = pending
            _atomic_write(evidence)

            result = await gateway.invoke(case["operation"], request)
            recorded = _result_record(case, request, result)
            records[records.index(pending)] = recorded
            by_case[case_id] = recorded
            _atomic_write(evidence)
            if result.error is not None and result.error.category in {
                GatewayErrorCategory.AUTH,
                GatewayErrorCategory.RATE,
                GatewayErrorCategory.SERVER,
                GatewayErrorCategory.TIMEOUT,
                GatewayErrorCategory.CONFIG,
            }:
                stop_reason = f"{result.error.category.value}:{case_id}"
                break
    finally:
        await gateway.aclose()

    evidence["sequence_complete"] = len(records) == len(planned) and all(
        item.get("state") == "RECORDED" for item in records
    )
    evidence["completed_at"] = (
        datetime.now(UTC).isoformat() if evidence["sequence_complete"] else None
    )
    evidence["stop_reason"] = stop_reason
    evidence["summary"] = {
        "planned": len(planned),
        "recorded": sum(item.get("state") == "RECORDED" for item in records),
        "ok": sum(item.get("status") == "OK" for item in records),
        "insufficient_evidence": sum(
            item.get("status") == "INSUFFICIENT_EVIDENCE" for item in records
        ),
        "failed": sum(item.get("status") == "FAILED" for item in records),
        "upstream_calls": sum(
            int(item.get("usage", {}).get("upstream_calls", 0)) for item in records
        ),
    }
    _atomic_write(evidence)
    print(
        json.dumps(
            {
                "sequence_complete": evidence["sequence_complete"],
                "summary": evidence["summary"],
                "stop_reason": stop_reason,
                "evidence": str(EVIDENCE_PATH),
            },
            ensure_ascii=False,
        )
    )
    return 0 if evidence["sequence_complete"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="send unrecorded T31 cases once"
    )
    parser.add_argument(
        "--prompt-pat",
        action="store_true",
        help="read KNODO_PAT once from a hidden prompt; never persist it",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER,
        help="private T31-only request ledger",
    )
    args = parser.parse_args()

    cases = _load_cases()
    planned = _validate_plan(cases)
    if not args.live:
        print(
            json.dumps(
                {
                    "mode": "DRY_RUN",
                    "cases": len(planned),
                    "request_hashes": {
                        case["case_id"]: _sha256(request) for case, request in planned
                    },
                    "operational_cap": OPERATIONAL_CAP,
                    "automatic_retries": 0,
                    "ledger": str(args.ledger),
                    "evidence": str(EVIDENCE_PATH),
                },
                ensure_ascii=False,
            )
        )
        return 0

    token_present = bool(os.environ.get("KNODO_PAT"))
    if not token_present and args.prompt_pat:
        token = getpass.getpass("Knodo PAT（隐藏输入，不会保存）: ")
        if token:
            os.environ["KNODO_PAT"] = token
            token_present = True
        token = ""
    if not token_present:
        print("KNODO_PAT unavailable; no live request sent.", file=sys.stderr)
        return 2
    return asyncio.run(_run_live(planned, _load_json(CONFIG_PATH), args.ledger))


if __name__ == "__main__":
    raise SystemExit(main())
