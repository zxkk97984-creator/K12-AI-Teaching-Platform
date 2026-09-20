"""Validate the versioned T31 synthetic evaluation set without network calls."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "teaching_cases.jsonl"
RUBRIC = ROOT / "evals" / "rubric.v1.json"
STAGES = {"PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"}
REQUIRED_CATEGORIES = {
    "source_supported_explanation",
    "wrong_answer_feedback",
    "active_opening",
    "no_source_boundary",
    "code_guidance",
}


def load_cases() -> list[dict]:
    cases = [
        json.loads(line)
        for line in CASES.read_text(encoding="utf-8").splitlines()
        if line
    ]
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case_id must be unique")
    if {case.get("stage") for case in cases} != STAGES:
        raise ValueError("the set must cover all four stages")
    if not REQUIRED_CATEGORIES <= {case.get("category") for case in cases}:
        raise ValueError("the set misses a required evaluation category")
    for case in cases:
        if not case.get("prompt") or not case.get("expected"):
            raise ValueError(f"case is incomplete: {case.get('case_id')}")
        if case.get("operation") not in {"TEACH_TURN", "CODE_FEEDBACK"}:
            raise ValueError(f"unsupported operation: {case.get('case_id')}")
    return cases


def build_report(cases: list[dict], rubric: dict) -> dict:
    return {
        "schema_version": "k12.teaching.eval-report.v1",
        "eval_set": "t31-local-v1",
        "mode": "OFFLINE_SYNTHETIC_NOT_KNODO",
        "cases": len(cases),
        "by_stage": dict(sorted(Counter(case["stage"] for case in cases).items())),
        "by_category": dict(
            sorted(Counter(case["category"] for case in cases).items())
        ),
        "rubric_dimensions": [item["id"] for item in rubric["dimensions"]],
        "automated_only": True,
        "human_review": "NOT_RUN",
        "live_platform": "LIVE_T31_COMPLETED_SEPARATE_EVIDENCE",
        "learning_effect_claim": "FORBIDDEN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = load_cases()
    rubric = json.loads(RUBRIC.read_text(encoding="utf-8"))
    report = build_report(cases, rubric)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
