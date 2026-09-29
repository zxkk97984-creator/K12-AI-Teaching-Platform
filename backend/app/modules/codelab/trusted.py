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


def _odd_even(data: dict[str, Any]) -> bool:
    if set(data) != {"number"}:
        raise ValueError("odd-even input must contain only number")
    number = data["number"]
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not -1_000_000 <= number <= 1_000_000
    ):
        raise ValueError("number must be an integer in the declared range")
    return number % 2 == 0


def _even_sum(data: dict[str, Any]) -> int:
    if set(data) != {"numbers"} or not isinstance(data["numbers"], list):
        raise ValueError("even-sum input must contain a numbers array")
    numbers = data["numbers"]
    if len(numbers) > 1000:
        raise ValueError("numbers exceeds the input limit")
    values = [_number(item) for item in numbers]
    if any(not isinstance(item, int) or not -1_000_000 <= item <= 1_000_000 for item in values):
        raise ValueError("numbers must be bounded integers")
    return sum(item for item in values if item % 2 == 0)


def _palindrome(data: dict[str, Any]) -> bool:
    if set(data) != {"text"} or not isinstance(data["text"], str) or len(data["text"]) > 1000:
        raise ValueError("palindrome input must contain a string of at most 1000 characters")
    return data["text"] == data["text"][::-1]


def _word_frequency(data: dict[str, Any]) -> dict[str, int]:
    if set(data) != {"words"} or not isinstance(data["words"], list):
        raise ValueError("word-frequency input must contain a words array")
    words = data["words"]
    if len(words) > 1000 or any(
        not isinstance(word, str)
        or not 1 <= len(word) <= 30
        or not word.isascii()
        or not word.islower()
        or not word.isalpha()
        for word in words
    ):
        raise ValueError("words must be short lowercase English words")
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return counts


def _prediction_accuracy(data: dict[str, Any]) -> float:
    if set(data) != {"y_true", "y_pred"}:
        raise ValueError("accuracy input must contain y_true and y_pred")
    actual = data["y_true"]
    predicted = data["y_pred"]
    if (
        not isinstance(actual, list)
        or not isinstance(predicted, list)
        or not actual
        or len(actual) != len(predicted)
        or len(actual) > 1000
        or any(type(value) is not int or not 0 <= value <= 9 for value in [*actual, *predicted])
    ):
        raise ValueError("labels must be equal non-empty lists of integers from 0 to 9")
    return sum(left == right for left, right in zip(actual, predicted, strict=True)) / len(actual)


def _sort_unique(data: dict[str, Any]) -> list[int]:
    if set(data) != {"numbers"} or not isinstance(data["numbers"], list):
        raise ValueError("sort-unique input must contain a numbers array")
    numbers = data["numbers"]
    if len(numbers) > 1000 or any(
        type(number) is not int or not -1_000_000 <= number <= 1_000_000 for number in numbers
    ):
        raise ValueError("numbers must be bounded integers")
    return sorted(set(numbers))


def _balanced_brackets(data: dict[str, Any]) -> bool:
    if (
        set(data) != {"text"}
        or not isinstance(data["text"], str)
        or len(data["text"]) > 1000
        or any(char not in "()[]{}" for char in data["text"])
    ):
        raise ValueError("bracket input must contain at most 1000 bracket characters")
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in data["text"]:
        if char in "([{":
            stack.append(char)
        elif not stack or stack.pop() != pairs[char]:
            return False
    return not stack


def _range_sum(data: dict[str, Any]) -> list[int]:
    if set(data) != {"numbers", "queries"}:
        raise ValueError("range-sum input must contain numbers and queries")
    numbers, queries = data["numbers"], data["queries"]
    if (
        not isinstance(numbers, list)
        or not 1 <= len(numbers) <= 1000
        or any(
            type(number) is not int or not -1_000_000 <= number <= 1_000_000 for number in numbers
        )
        or not isinstance(queries, list)
        or len(queries) > 1000
    ):
        raise ValueError("invalid numbers or queries")
    answers = []
    for query in queries:
        if (
            not isinstance(query, list)
            or len(query) != 2
            or type(query[0]) is not int
            or type(query[1]) is not int
            or not 0 <= query[0] <= query[1] < len(numbers)
        ):
            raise ValueError("each query must be a valid inclusive [left, right] pair")
        answers.append(sum(numbers[query[0] : query[1] + 1]))
    return answers


def _climbing_stairs(data: dict[str, Any]) -> int:
    if set(data) != {"n"} or type(data["n"]) is not int or not 0 <= data["n"] <= 30:
        raise ValueError("n must be an integer from 0 to 30")
    ways = [1, 1]
    for _ in range(2, data["n"] + 1):
        ways.append(ways[-1] + ways[-2])
    return ways[data["n"]]


_ORACLES: dict[str, Callable[[dict[str, Any]], Any]] = {
    "temperature-converter": _temperature,
    "list-summary": _summary,
    "binary-search": _binary_search,
    "odd-even": _odd_even,
    "even-sum": _even_sum,
    "palindrome-check": _palindrome,
    "word-frequency": _word_frequency,
    "prediction-accuracy": _prediction_accuracy,
    "sort-unique": _sort_unique,
    "balanced-brackets": _balanced_brackets,
    "range-sum": _range_sum,
    "climbing-stairs": _climbing_stairs,
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
    "odd-even": (
        TrustedCase("f1-1", "F1", {"number": -4}),
        TrustedCase("f1-2", "F1", {"number": 9}),
        TrustedCase("f1-3", "F1", {"number": 0}),
        TrustedCase("f2-1", "F2", {"number": 1}),
        TrustedCase("f2-2", "F2", {"number": -1}),
        TrustedCase("f2-3", "F2", {"number": 2}),
        TrustedCase("r1-1", "R1", {"number": -1_000_000}),
        TrustedCase("r1-2", "R1", {"number": 1_000_000}),
    ),
    "even-sum": (
        TrustedCase("f1-1", "F1", {"numbers": [1, 2, 3, 4]}),
        TrustedCase("f1-2", "F1", {"numbers": [0, -2, 5]}),
        TrustedCase("f1-3", "F1", {"numbers": [7]}),
        TrustedCase("f2-1", "F2", {"numbers": [-3, -4, 6]}),
        TrustedCase("f2-2", "F2", {"numbers": [2, 2, 3]}),
        TrustedCase("f2-3", "F2", {"numbers": [1, 3, 5]}),
        TrustedCase("r1-1", "R1", {"numbers": []}),
        TrustedCase("r1-2", "R1", {"numbers": [-1_000_000, 1_000_000]}),
    ),
    "palindrome-check": (
        TrustedCase("f1-1", "F1", {"text": "level"}),
        TrustedCase("f1-2", "F1", {"text": "Level"}),
        TrustedCase("f1-3", "F1", {"text": "abca"}),
        TrustedCase("f2-1", "F2", {"text": "上海自来水来自海上"}),
        TrustedCase("f2-2", "F2", {"text": "a b a"}),
        TrustedCase("f2-3", "F2", {"text": "racecar!"}),
        TrustedCase("r1-1", "R1", {"text": ""}),
        TrustedCase("r1-2", "R1", {"text": "x"}),
    ),
    "word-frequency": (
        TrustedCase("f1-1", "F1", {"words": ["ai", "python", "ai"]}),
        TrustedCase("f1-2", "F1", {"words": ["code", "lab"]}),
        TrustedCase("f1-3", "F1", {"words": ["a", "a", "a"]}),
        TrustedCase("f2-1", "F2", {"words": ["red", "blue", "red", "green"]}),
        TrustedCase("f2-2", "F2", {"words": ["x", "y", "x", "z", "y"]}),
        TrustedCase("f2-3", "F2", {"words": ["python"]}),
        TrustedCase("r1-1", "R1", {"words": []}),
        TrustedCase("r1-2", "R1", {"words": ["a" * 30, "a" * 30]}),
    ),
    "prediction-accuracy": (
        TrustedCase("f1-1", "F1", {"y_true": [1, 0, 1, 1], "y_pred": [1, 0, 0, 1]}),
        TrustedCase("f1-2", "F1", {"y_true": [1, 2, 3], "y_pred": [1, 2, 3]}),
        TrustedCase("f1-3", "F1", {"y_true": [0, 0], "y_pred": [1, 1]}),
        TrustedCase("f2-1", "F2", {"y_true": [2, 3, 4], "y_pred": [2, 0, 4]}),
        TrustedCase("f2-2", "F2", {"y_true": [9, 0, 5, 5], "y_pred": [0, 0, 5, 6]}),
        TrustedCase("f2-3", "F2", {"y_true": [7], "y_pred": [7]}),
        TrustedCase("r1-1", "R1", {"y_true": [0], "y_pred": [1]}),
        TrustedCase(
            "r1-2",
            "R1",
            {"y_true": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], "y_pred": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]},
        ),
    ),
    "sort-unique": (
        TrustedCase("f1-1", "F1", {"numbers": [3, 1, 3, 2]}),
        TrustedCase("f1-2", "F1", {"numbers": [5, 4, 3]}),
        TrustedCase("f1-3", "F1", {"numbers": [1, 2, 3]}),
        TrustedCase("f2-1", "F2", {"numbers": [-2, 0, -2, 2]}),
        TrustedCase("f2-2", "F2", {"numbers": [8, 8, 8]}),
        TrustedCase("f2-3", "F2", {"numbers": [9, -1, 0]}),
        TrustedCase("r1-1", "R1", {"numbers": []}),
        TrustedCase("r1-2", "R1", {"numbers": [-1_000_000, 1_000_000]}),
    ),
    "balanced-brackets": (
        TrustedCase("f1-1", "F1", {"text": "{[()]}"}),
        TrustedCase("f1-2", "F1", {"text": "([)]"}),
        TrustedCase("f1-3", "F1", {"text": "((()))"}),
        TrustedCase("f2-1", "F2", {"text": "([{}])"}),
        TrustedCase("f2-2", "F2", {"text": "((]"}),
        TrustedCase("f2-3", "F2", {"text": "{}[]()"}),
        TrustedCase("r1-1", "R1", {"text": ""}),
        TrustedCase("r1-2", "R1", {"text": "("}),
    ),
    "range-sum": (
        TrustedCase("f1-1", "F1", {"numbers": [1, 2, 3, 4], "queries": [[0, 1], [1, 3]]}),
        TrustedCase("f1-2", "F1", {"numbers": [5], "queries": [[0, 0]]}),
        TrustedCase("f1-3", "F1", {"numbers": [1, 2, 3], "queries": [[0, 2]]}),
        TrustedCase("f2-1", "F2", {"numbers": [-3, 1, -2], "queries": [[0, 1], [1, 2]]}),
        TrustedCase("f2-2", "F2", {"numbers": [4, 4, 4], "queries": [[1, 1], [0, 2]]}),
        TrustedCase("f2-3", "F2", {"numbers": [0, -5, 5], "queries": [[2, 2]]}),
        TrustedCase("r1-1", "R1", {"numbers": [1], "queries": []}),
        TrustedCase("r1-2", "R1", {"numbers": [-1_000_000, 1_000_000], "queries": [[0, 1]]}),
    ),
    "climbing-stairs": (
        TrustedCase("f1-1", "F1", {"n": 0}),
        TrustedCase("f1-2", "F1", {"n": 1}),
        TrustedCase("f1-3", "F1", {"n": 2}),
        TrustedCase("f2-1", "F2", {"n": 3}),
        TrustedCase("f2-2", "F2", {"n": 5}),
        TrustedCase("f2-3", "F2", {"n": 10}),
        TrustedCase("r1-1", "R1", {"n": 29}),
        TrustedCase("r1-2", "R1", {"n": 30}),
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
