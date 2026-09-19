#!/usr/bin/env python3
"""Validate T01 planning data. This validates design metadata, not content quality."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
SOURCE_ROOT = Path("/home/zxk/Projects/K12-Learning-platform")


def load(name: str) -> dict[str, Any]:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def derive_stage(grade: int) -> str:
    if isinstance(grade, bool) or not isinstance(grade, int):
        raise ValueError("grade must be an integer")
    if 1 <= grade <= 3:
        return "PRIMARY_LOWER"
    if 4 <= grade <= 6:
        return "PRIMARY_UPPER"
    if 7 <= grade <= 9:
        return "JUNIOR"
    if 10 <= grade <= 12:
        return "SENIOR"
    raise ValueError("grade must be between 1 and 12")


def resolve_stage(grade: int | None, selected_stage: str | None) -> tuple[str, int | None]:
    if grade is None:
        if selected_stage not in {"PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"}:
            raise ValueError("stage required when grade is unknown")
        return selected_stage, None
    stage = derive_stage(grade)
    if selected_stage is not None and selected_stage != stage:
        raise ValueError("grade and stage conflict")
    return stage, grade


def main() -> int:
    failures: list[str] = []
    req = load("requirements-matrix.json")
    mig = load("migration-scope.json")
    inventory = load("course-inventory.json")
    showcase = load("showcase-chapters.json")

    expected_boundaries = {1: "PRIMARY_LOWER", 3: "PRIMARY_LOWER", 4: "PRIMARY_UPPER", 6: "PRIMARY_UPPER", 7: "JUNIOR", 9: "JUNIOR", 10: "SENIOR", 12: "SENIOR"}
    for grade, expected in expected_boundaries.items():
        try:
            actual = derive_stage(grade)
        except Exception as exc:
            failures.append(f"grade {grade} raised {exc}")
        else:
            if actual != expected:
                failures.append(f"grade {grade}: {actual} != {expected}")
    for bad in (0, 13, "6", True, None):
        try:
            derive_stage(bad)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            failures.append(f"invalid grade accepted: {bad!r}")
    if resolve_stage(None, "JUNIOR") != ("JUNIOR", None):
        failures.append("stage-only path invented a grade")

    selected = {r.get("modality") for r in req["requirements"] if r.get("scope") == "R1"}
    required = {"DIALOGUE", "TEACHING_RESOURCE", "ANIMATION", "ONLINE_CODE", "GAME_QUIZ"}
    if required - selected:
        failures.append(f"missing R1 modalities: {sorted(required-selected)}")
    if req["optional_modalities"] != ["PICTURE_BOOK"]:
        failures.append("picture book must remain optional")

    allowed = set(mig["allowed_dispositions"])
    seen = {m["capability"] for m in mig["items"]}
    for item in mig["items"]:
        if item["disposition"] not in allowed:
            failures.append(f"bad disposition: {item}")
    for required_capability in ("记忆", "语音", "CodeLab", "推荐", "学段"):
        if not any(required_capability in capability for capability in seen):
            failures.append(f"migration scope omits {required_capability}")

    if inventory["count"] != 25 or len(inventory["books"]) != 25:
        failures.append("inventory is not exactly 25 books")
    if any(book["grade_min"] < 3 for book in inventory["books"]):
        failures.append("inventory unexpectedly contains grade 1–2 content")
    if inventory["gaps"]["primary_lower_grade_1_2"]["status"] != "MISSING_EXISTING_CONTENT":
        failures.append("grade 1–2 gap not marked")

    chapters = showcase["chapters"]
    stages = [c["stage"] for c in chapters]
    if sorted(stages) != sorted(["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"]):
        failures.append("showcase must contain exactly one chapter per stage")
    for chapter in chapters:
        if chapter["grade_min"] != {"PRIMARY_LOWER": 1, "PRIMARY_UPPER": 4, "JUNIOR": 7, "SENIOR": 10}[chapter["stage"]]:
            failures.append(f"unexpected grade_min for {chapter['stage']}")
        if chapter["source_status"] == "NEW_SOURCE_REQUIRED":
            if chapter["source_path"] is not None:
                failures.append(f"new chapter incorrectly points at old source: {chapter['chapter_id']}")
        else:
            source = SOURCE_ROOT / chapter["source_path"]
            if not source.is_file():
                failures.append(f"reused chapter source missing: {source}")
    if len(showcase["animations"]) < 2:
        failures.append("fewer than two deterministic animation templates")

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: T01 requirements, migration scope, 25-book inventory and four showcase stages are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
