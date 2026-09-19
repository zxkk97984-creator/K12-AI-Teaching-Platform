"""Trusted task oracles and hidden case manifests.

This module is backend/runner-side only. It is never serialized by
``public_task_view``. The cases contain inputs only; expected values are
computed by these trusted functions, so a student-provided stdout or
``passed`` counter has no bearing on the verdict.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.modules.codelab.contracts import canonical_json


@dataclass(frozen=True)
class TrustedCase:
    case_id: str
    group_id: str
    input: dict[str, Any]

    def manifest_record(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "group_id": self.group_id, "input": self.input}


def _number(value: Any) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a JSON number")
    if not math.isfinite(float(value)):
        raise ValueError("non-finite numbers are not valid JSON inputs")
    return value


def _temperature(data: dict[str, Any]) -> float:
    if set(data) != {"celsius"}:
        raise ValueError("temperature input must contain only celsius")
    celsius = _number(data["celsius"])
    return celsius * 9 / 5 + 32


def _summary(data: dict[str, Any]) -> dict[str, Any]:
    if set(data) != {"numbers"} or not isinstance(data["numbers"], list):
        raise ValueError("summary input must contain a numbers array")
    numbers = [_number(value) for value in data["numbers"]]
    if len(numbers) > 100:
        raise ValueError("numbers exceeds the input limit")
    if not numbers:
        return {"count": 0, "sum": 0, "max": None, "min": None, "mean": None}
    total = sum(numbers)
    return {
        "count": len(numbers),
        "sum": total,
        "max": max(numbers),
        "min": min(numbers),
        "mean": total / len(numbers),
    }


def _binary_search(data: dict[str, Any]) -> int:
    if set(data) != {"items", "target"} or not isinstance(data["items"], list):
        raise ValueError("binary search input must contain items and target")
    items = [_number(value) for value in data["items"]]
    target = _number(data["target"])
    if any(left >= right for left, right in zip(items, items[1:], strict=False)):
        raise ValueError("items must be strictly increasing")
    low, high = 0, len(items) - 1
    while low <= high:
        middle = low + (high - low) // 2
        if items[middle] == target:
            return middle
        if items[middle] < target:
            low = middle + 1
        else:
            high = middle - 1
    return -1


_ORACLES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "temperature-converter": _temperature,
    "list-summary": _summary,
    "binary-search": _binary_search,
}

_CASES: dict[str, tuple[TrustedCase, ...]] = {
    "temperature-converter": (
        TrustedCase("f1-freezing", "F1", {"celsius": 0}),
        TrustedCase("f1-boiling", "F1", {"celsius": 100}),
        TrustedCase("f1-body", "F1", {"celsius": 37}),
        TrustedCase("f2-below-zero", "F2", {"celsius": -10}),
        TrustedCase("f2-minus-forty", "F2", {"celsius": -40}),
        TrustedCase("f2-decimal", "F2", {"celsius": 36.6}),
        TrustedCase("r1-number", "R1", {"celsius": 20}),
        TrustedCase("r1-decimal-number", "R1", {"celsius": 0.5}),
    ),
    "list-summary": (
        TrustedCase("f1-basic", "F1", {"numbers": [1, 2, 3]}),
        TrustedCase("f1-single", "F1", {"numbers": [5]}),
        TrustedCase("f2-negative", "F2", {"numbers": [-3, -1, -7]}),
        TrustedCase("f2-one", "F2", {"numbers": [42]}),
        TrustedCase("r1-empty", "R1", {"numbers": []}),
    ),
    "binary-search": (
        TrustedCase("f1-middle", "F1", {"items": [1, 3, 5, 7, 9], "target": 5}),
        TrustedCase("f1-last", "F1", {"items": [1, 3, 5, 7, 9], "target": 9}),
        TrustedCase("f1-first", "F1", {"items": [1, 3, 5, 7, 9], "target": 1}),
        TrustedCase("f2-missing-middle", "F2", {"items": [1, 3, 5, 7, 9], "target": 4}),
        TrustedCase("f2-smaller", "F2", {"items": [1, 3, 5, 7, 9], "target": 0}),
        TrustedCase("f2-larger", "F2", {"items": [1, 3, 5, 7, 9], "target": 100}),
        TrustedCase("f2-single", "F2", {"items": [8], "target": 8}),
        TrustedCase("r1-empty", "R1", {"items": [], "target": 5}),
    ),
}


def trusted_cases(task_id: str) -> tuple[TrustedCase, ...]:
    try:
        return _CASES[task_id]
    except KeyError as exc:
        raise KeyError(f"no trusted oracle registered for {task_id}") from exc


def trusted_cases_sha256(task_id: str) -> str:
    records = [case.manifest_record() for case in trusted_cases(task_id)]
    return hashlib.sha256(canonical_json(records).encode()).hexdigest()


def expected_output(task_id: str, input_value: dict[str, Any]) -> Any:
    try:
        oracle = _ORACLES[task_id]
    except KeyError as exc:
        raise KeyError(f"no trusted oracle registered for {task_id}") from exc
    return oracle(input_value)


def validate_trusted_manifest(task_id: str, *, expected_count: int, expected_sha256: str) -> None:
    cases = trusted_cases(task_id)
    actual = trusted_cases_sha256(task_id)
    if len(cases) != expected_count or actual != expected_sha256:
        raise ValueError(f"trusted case manifest mismatch for {task_id}")
