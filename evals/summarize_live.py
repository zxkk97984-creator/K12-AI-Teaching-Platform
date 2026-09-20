"""Summarize T31 live evidence without making network requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "docs" / "acceptance" / "T31-live-results.synthetic.json"
DEFAULT_OUTPUT = ROOT / "docs" / "acceptance" / "T31-live-summary.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile_nearest_rank(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def build_summary(evidence: dict[str, Any], *, evidence_sha256: str) -> dict[str, Any]:
    records = evidence.get("records")
    if not isinstance(records, list) or len(records) != 16:
        raise ValueError("T31 live evidence must contain exactly 16 records")
    if not evidence.get("sequence_complete"):
        raise ValueError("T31 live evidence sequence is incomplete")
    if any(record.get("state") != "RECORDED" for record in records):
        raise ValueError("T31 live evidence contains a non-terminal record")

    durations = [int(record["usage"]["duration_ms"]) for record in records]
    status_counts = Counter(str(record.get("status")) for record in records)
    errors = Counter(
        (
            str(record["error"].get("category")),
            str(record["error"].get("reason_code")),
        )
        for record in records
        if isinstance(record.get("error"), dict)
    )
    models = sorted(
        {
            str(record["remote_metadata"]["model"])
            for record in records
            if isinstance(record.get("remote_metadata"), dict)
            and record["remote_metadata"].get("model")
        }
    )
    token_totals = {
        key: sum(
            int((record.get("remote_metadata") or {}).get(key, 0))
            for record in records
            if isinstance(record.get("remote_metadata"), dict)
        )
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }

    case_results: list[dict[str, Any]] = []
    for record in records:
        response = record.get("response") or {}
        error = record.get("error") or {}
        checks = record.get("automated_checks") or {}
        case_results.append(
            {
                "case_id": record["case_id"],
                "stage": record["stage"],
                "category": record["category"],
                "operation": record["operation"],
                "status": record["status"],
                "error_category": error.get("category"),
                "error_reason_code": error.get("reason_code"),
                "duration_ms": record["usage"]["duration_ms"],
                "source_ref_count": len(response.get("source_refs", [])),
                "warnings": response.get("warnings", []),
                "automated_checks_passed": bool(checks) and all(checks.values()),
                "human_review": "NOT_RUN",
            }
        )

    successful = [record for record in records if record.get("status") == "OK"]
    published_successful = [
        record
        for record in successful
        if record.get("source_kind") == "PUBLISHED_CHAPTER"
    ]
    no_source_successful = [
        record for record in successful if record.get("source_kind") == "NO_SOURCE"
    ]
    return {
        "schema_version": "k12.t31.live-summary.v1",
        "eval_set": evidence["eval_set"],
        "source_evidence_sha256": evidence_sha256,
        "data_class": evidence["data_class"],
        "sequence_complete": True,
        "planned_cases": 16,
        "recorded_cases": 16,
        "status_counts": dict(sorted(status_counts.items())),
        "valid_response_rate": len(successful) / 16,
        "errors": [
            {"category": category, "reason_code": reason, "count": count}
            for (category, reason), count in sorted(errors.items())
        ],
        "coverage": {
            "by_stage": dict(
                sorted(Counter(record["stage"] for record in records).items())
            ),
            "by_category": dict(
                sorted(Counter(record["category"] for record in records).items())
            ),
            "by_operation": dict(
                sorted(Counter(record["operation"] for record in records).items())
            ),
        },
        "latency_ms": {
            "min": min(durations),
            "median": int(statistics.median(durations)),
            "p95_nearest_rank": _percentile_nearest_rank(durations, 0.95),
            "max": max(durations),
            "total": sum(durations),
        },
        "upstream_calls": sum(
            int(record["usage"]["upstream_calls"]) for record in records
        ),
        "models": models,
        "upstream_reported_tokens": token_totals,
        "token_usage_interpretation": (
            "UNAVAILABLE_OR_UNRELIABLE"
            if not any(token_totals.values())
            else "REPORTED"
        ),
        "automated_boundaries": {
            "successful_published_cases_with_source_refs": sum(
                bool((record.get("response") or {}).get("source_refs"))
                for record in published_successful
            ),
            "successful_published_cases": len(published_successful),
            "successful_no_source_cases_with_zero_refs": sum(
                not (record.get("response") or {}).get("source_refs")
                for record in no_source_successful
            ),
            "successful_no_source_cases": len(no_source_successful),
            "successful_outputs_passing_all_automated_checks": sum(
                all((record.get("automated_checks") or {}).values())
                for record in successful
            ),
        },
        "human_review": "NOT_RUN",
        "cost": "UNKNOWN_NO_TRUSTWORTHY_USAGE_OR_CURRENCY_SOURCE",
        "learning_effect_claim": "FORBIDDEN",
        "case_results": case_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    evidence = json.loads(args.input.read_text(encoding="utf-8"))
    summary = build_summary(evidence, evidence_sha256=_sha256(args.input))
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"output": str(args.output), "status_counts": summary["status_counts"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
