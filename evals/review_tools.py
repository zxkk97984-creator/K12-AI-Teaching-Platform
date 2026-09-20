"""Build and validate the T31 human-review handoff artifacts."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "teaching_cases.jsonl"
RUBRIC_PATH = ROOT / "evals" / "rubric.v1.json"
RAW_PATH = ROOT / "docs" / "acceptance" / "T31-live-results.synthetic.json"
SUMMARY_PATH = ROOT / "docs" / "acceptance" / "T31-live-summary.json"
TEMPLATE_PATH = ROOT / "docs" / "acceptance" / "T31-human-review.template.json"
PACKET_PATH = ROOT / "docs" / "acceptance" / "T31-review-packet.local.md"
SCHEMA_VERSION = "k12.t31.human-review.v1"
ATTESTATION = "本人已审阅全部16条合成评测记录，并对本次人工判断负责。"
CONCLUSIONS = {"PASS", "NEEDS_REVISION", "FAIL"}


class ReviewValidationError(ValueError):
    """The human-review artifact is incomplete or inconsistent."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReviewValidationError(f"expected JSON object: {path}")
    return value


def _load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _dimensions() -> list[str]:
    rubric = _load_json(RUBRIC_PATH)
    return [str(item["id"]) for item in rubric["dimensions"]]


def build_template() -> dict[str, Any]:
    cases = _load_cases()
    summary = _load_json(SUMMARY_PATH)
    results = {item["case_id"]: item for item in summary["case_results"]}
    dimensions = _dimensions()
    return {
        "schema_version": SCHEMA_VERSION,
        "eval_set": "t31-local-v1",
        "source_evidence_sha256": summary["source_evidence_sha256"],
        "review_status": "NOT_RUN",
        "reviewer": {"name": None, "role_or_org": None},
        "reviewed_at": None,
        "attestation": None,
        "case_reviews": [
            {
                "case_id": case["case_id"],
                "live_status": results[case["case_id"]]["status"],
                "scores": {dimension: None for dimension in dimensions},
                "disposition": None,
                "rationale": "",
            }
            for case in cases
        ],
        "overall": {
            "accept_failed_cases_for_demo": None,
            "four_stage_age_fit": None,
            "source_support_sufficient": None,
            "code_feedback_boundary_preserved": None,
            "conclusion": None,
            "rationale": "",
            "traceable_signature": None,
        },
    }


def validate_template(review: dict[str, Any]) -> None:
    expected = build_template()
    if review != expected:
        raise ReviewValidationError(
            "template drift: rebuild with `python evals/review_tools.py build`"
        )


def _required_text(value: Any, field: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ReviewValidationError(
            f"{field} must contain at least {minimum} characters"
        )
    return value.strip()


def _validate_reviewed_at(value: Any) -> str:
    rendered = _required_text(value, "reviewed_at")
    try:
        datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewValidationError("reviewed_at must be ISO-8601") from exc
    return rendered


def validate_completed(review: dict[str, Any]) -> dict[str, Any]:
    template = build_template()
    if review.get("schema_version") != SCHEMA_VERSION:
        raise ReviewValidationError("schema_version mismatch")
    if review.get("eval_set") != template["eval_set"]:
        raise ReviewValidationError("eval_set mismatch")
    if review.get("source_evidence_sha256") != template["source_evidence_sha256"]:
        raise ReviewValidationError("source evidence hash mismatch")
    if review.get("review_status") != "COMPLETE":
        raise ReviewValidationError("review_status must be COMPLETE")

    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict):
        raise ReviewValidationError("reviewer must be an object")
    reviewer_name = _required_text(reviewer.get("name"), "reviewer.name", minimum=2)
    reviewer_role = _required_text(
        reviewer.get("role_or_org"), "reviewer.role_or_org", minimum=2
    )
    reviewed_at = _validate_reviewed_at(review.get("reviewed_at"))
    if review.get("attestation") != ATTESTATION:
        raise ReviewValidationError("attestation text is missing or changed")

    expected_cases = template["case_reviews"]
    case_reviews = review.get("case_reviews")
    if not isinstance(case_reviews, list) or len(case_reviews) != len(expected_cases):
        raise ReviewValidationError("case_reviews must contain all 16 cases")
    dimensions = _dimensions()
    dimension_scores: dict[str, list[int]] = defaultdict(list)
    for expected, actual in zip(expected_cases, case_reviews, strict=True):
        if not isinstance(actual, dict):
            raise ReviewValidationError("each case review must be an object")
        case_id = expected["case_id"]
        if (
            actual.get("case_id") != case_id
            or actual.get("live_status") != expected["live_status"]
        ):
            raise ReviewValidationError(f"case identity/status mismatch: {case_id}")
        scores = actual.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(dimensions):
            raise ReviewValidationError(f"score dimensions mismatch: {case_id}")
        for dimension in dimensions:
            score = scores[dimension]
            if (
                isinstance(score, bool)
                or not isinstance(score, int)
                or score not in {0, 1, 2}
            ):
                raise ReviewValidationError(f"invalid {dimension} score: {case_id}")
            dimension_scores[dimension].append(score)
        disposition = actual.get("disposition")
        if disposition not in CONCLUSIONS:
            raise ReviewValidationError(f"invalid disposition: {case_id}")
        needs_reason = (
            disposition != "PASS"
            or expected["live_status"] != "OK"
            or any(score < 2 for score in scores.values())
        )
        _required_text(
            actual.get("rationale"),
            f"case rationale: {case_id}",
            minimum=8 if needs_reason else 2,
        )

    overall = review.get("overall")
    if not isinstance(overall, dict):
        raise ReviewValidationError("overall must be an object")
    for field in (
        "accept_failed_cases_for_demo",
        "four_stage_age_fit",
        "source_support_sufficient",
        "code_feedback_boundary_preserved",
    ):
        if not isinstance(overall.get(field), bool):
            raise ReviewValidationError(f"overall.{field} must be boolean")
    conclusion = overall.get("conclusion")
    if conclusion not in CONCLUSIONS:
        raise ReviewValidationError("overall.conclusion is invalid")
    overall_rationale = _required_text(
        overall.get("rationale"), "overall.rationale", minimum=20
    )
    signature = _required_text(
        overall.get("traceable_signature"), "overall.traceable_signature", minimum=4
    )

    return {
        "schema_version": "k12.t31.human-review-result.v1",
        "eval_set": review["eval_set"],
        "source_evidence_sha256": review["source_evidence_sha256"],
        "reviewer": {"name": reviewer_name, "role_or_org": reviewer_role},
        "reviewed_at": reviewed_at,
        "dimension_averages": {
            dimension: sum(scores) / len(scores)
            for dimension, scores in sorted(dimension_scores.items())
        },
        "case_dispositions": dict(
            sorted(
                _counter_like(actual["disposition"] for actual in case_reviews).items()
            )
        ),
        "overall_conclusion": conclusion,
        "overall_rationale": overall_rationale,
        "traceable_signature": signature,
        "human_review": "COMPLETE",
    }


def _counter_like(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def render_packet() -> str:
    cases = _load_cases()
    raw = _load_json(RAW_PATH)
    records = {item["case_id"]: item for item in raw["records"]}
    lines = [
        "# T31 真人审核包（本机合成原始证据）",
        "",
        "本文件不提交 Git。请逐条对照 `T31-human-review.template.json` 评分。",
        "",
    ]
    for case in cases:
        record = records[case["case_id"]]
        response = record.get("response") or {}
        error = record.get("error") or {}
        lines.extend(
            [
                f"## {case['case_id']} · {case['stage']} · {case['category']}",
                "",
                f"- operation: `{case['operation']}`",
                f"- live status: `{record['status']}`",
                f"- error: `{error.get('category') or 'none'} / {error.get('reason_code') or 'none'}`",
                f"- expected: `{json.dumps(case['expected'], ensure_ascii=False, sort_keys=True)}`",
                f"- prompt: {case['prompt']}",
                "",
                "### Response",
                "",
                str(
                    response.get("message_markdown")
                    or "（没有通过冻结 Schema 的可审阅响应）"
                ),
                "",
                f"- followup: {response.get('followup_question') or 'none'}",
                f"- source_refs: `{json.dumps(response.get('source_refs', []), ensure_ascii=False)}`",
                f"- warnings: `{json.dumps(response.get('warnings', []), ensure_ascii=False)}`",
                "",
                "### Reviewer notes",
                "",
                "- factuality (0-2):",
                "- source_support (0-2):",
                "- age_fit (0-2):",
                "- pedagogical_actionability (0-2):",
                "- safety_boundary (0-2):",
                "- disposition:",
                "- rationale:",
                "",
            ]
        )
    return "\n".join(lines)


def _write(path: Path, content: str, *, mode: int = 0o664) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build")
    subparsers.add_parser("check-template")
    check_review = subparsers.add_parser("check-review")
    check_review.add_argument("--review", type=Path, required=True)
    check_review.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.command == "build":
        template = build_template()
        _write(TEMPLATE_PATH, json.dumps(template, ensure_ascii=False, indent=2) + "\n")
        _write(PACKET_PATH, render_packet(), mode=0o600)
        print(json.dumps({"template": str(TEMPLATE_PATH), "packet": str(PACKET_PATH)}))
        return 0
    if args.command == "check-template":
        validate_template(_load_json(TEMPLATE_PATH))
        print("PASS: T31 human-review template is current and unsigned.")
        return 0

    result = validate_completed(_load_json(args.review))
    if args.output:
        _write(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
