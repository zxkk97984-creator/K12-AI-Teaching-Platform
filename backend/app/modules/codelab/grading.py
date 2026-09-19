from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from app.modules.codelab.contracts import TaskDefinition
from app.modules.codelab.trusted import expected_output, trusted_cases

ExecutionStatus = Literal[
    "COMPLETED",
    "STUDENT_EXCEPTION",
    "INVALID_JSON",
    "TIMEOUT",
    "OUTPUT_LIMIT",
    "RUNNER_ERROR",
    "NOT_RUN",
    "NO_TESTS",
]
GradeStatus = Literal["PASSED", "PARTIAL", "FAILED", "NOT_VERIFIED", "SYSTEM_ERROR"]
_STUDENT_FAILURES = {"STUDENT_EXCEPTION", "INVALID_JSON", "TIMEOUT", "OUTPUT_LIMIT"}
_NON_VERIFIED = {"NOT_RUN", "NO_TESTS"}
_VALID_EXECUTION_STATUSES = {"COMPLETED", "RUNNER_ERROR", *_STUDENT_FAILURES, *_NON_VERIFIED}


@dataclass(frozen=True)
class GroupResult:
    group_id: str
    dimension: Literal["F", "R"]
    max_score: float
    passed: int
    failed: int
    errors: int
    score: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.group_id,
            "dimension": self.dimension,
            "max_score": self.max_score,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "score": self.score,
        }


@dataclass(frozen=True)
class GradingResult:
    task_id: str
    task_revision: int
    status: GradeStatus
    deterministic_tests_available: bool
    deterministic_score: float | None
    groups: tuple[GroupResult, ...]
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "k12.grading-result.v1",
            "task_id": self.task_id,
            "task_revision": self.task_revision,
            "status": self.status,
            "deterministic_tests_available": self.deterministic_tests_available,
            "deterministic_score": self.deterministic_score,
            "score_scale": 70,
            "groups": [group.as_dict() for group in self.groups],
            "errors": list(self.errors),
        }


def _same_json(expected: Any, actual: Any, *, tolerance: float = 1e-6) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isfinite(float(actual)) and abs(float(expected) - float(actual)) <= tolerance
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            _same_json(expected[key], actual[key], tolerance=tolerance) for key in expected
        )
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(
            _same_json(left, right, tolerance=tolerance)
            for left, right in zip(expected, actual, strict=True)
        )
    return expected == actual


def _observation_map(
    observations: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    mapped: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for observation in observations:
        case_id = observation.get("case_id") if isinstance(observation, dict) else None
        if not isinstance(case_id, str) or not case_id:
            errors.append("runner observation is missing case_id")
            continue
        if case_id in mapped:
            errors.append(f"duplicate runner observation: {case_id}")
            continue
        mapped[case_id] = observation
    return mapped, errors


def grade_observations(
    task_id: str,
    task_revision: int,
    observations: list[dict[str, Any]],
    group_definitions: dict[str, tuple[Literal["F", "R"], float]] | None = None,
) -> GradingResult:
    """Grade runner observations using only trusted expected outputs.

    ``stdout``, ``reported_passed`` and other student-controlled fields are
    intentionally ignored. Runner/system faults do not become a student zero.
    """

    cases = trusted_cases(task_id)
    if not cases:
        return GradingResult(
            task_id, task_revision, "NOT_VERIFIED", False, None, (), ("no trusted tests",)
        )

    mapped, structural_errors = _observation_map(observations)
    known_case_ids = {case.case_id for case in cases}
    structural_errors.extend(
        f"unknown runner observation: {case_id}"
        for case_id in mapped
        if case_id not in known_case_ids
    )
    if structural_errors:
        return GradingResult(
            task_id,
            task_revision,
            "SYSTEM_ERROR",
            True,
            None,
            (),
            tuple(structural_errors[:4]),
        )

    grouped: dict[str, list[tuple[str, bool, str | None]]] = defaultdict(list)
    not_verified = False
    system_error = False
    errors: list[str] = []
    for case in cases:
        observation = mapped.get(case.case_id)
        if observation is None:
            not_verified = True
            errors.append(f"missing trusted observation: {case.case_id}")
            continue
        status: ExecutionStatus = observation.get("execution_status", "RUNNER_ERROR")
        if not isinstance(status, str) or status not in _VALID_EXECUTION_STATUSES:
            system_error = True
            errors.append(f"unknown runner status: {case.case_id}")
            continue
        if status in _NON_VERIFIED:
            not_verified = True
            errors.append(f"test not run: {case.case_id}")
            continue
        if status == "RUNNER_ERROR":
            system_error = True
            errors.append(f"runner system error: {case.case_id}")
            continue
        passed = False
        if status == "COMPLETED" and "actual_output" in observation:
            try:
                passed = _same_json(
                    expected_output(task_id, case.input), observation["actual_output"]
                )
            except (TypeError, ValueError, OverflowError):
                system_error = True
                errors.append(f"trusted oracle error: {case.case_id}")
                continue
        grouped[case.group_id].append((case.case_id, passed, None if passed else status))

    if system_error:
        return GradingResult(
            task_id, task_revision, "SYSTEM_ERROR", True, None, (), tuple(errors[:4])
        )
    if not_verified:
        return GradingResult(
            task_id, task_revision, "NOT_VERIFIED", True, None, (), tuple(errors[:4])
        )

    group_definitions = group_definitions or {
        "F1": ("F", 30.0),
        "F2": ("F", 30.0),
        "R1": ("R", 10.0),
    }
    results: list[GroupResult] = []
    total = 0.0
    total_possible = 0.0
    for group_id, (dimension, max_score) in group_definitions.items():
        cases_in_group = grouped.get(group_id, [])
        passed = sum(1 for _, is_passed, _ in cases_in_group if is_passed)
        failed = len(cases_in_group) - passed
        score = max_score * passed / len(cases_in_group) if cases_in_group else None
        if score is not None:
            total += score
            total_possible += max_score
        results.append(GroupResult(group_id, dimension, max_score, passed, failed, 0, score))

    score = round(total, 4)
    status: GradeStatus
    if total_possible == 0:
        status = "NOT_VERIFIED"
        score_value: float | None = None
    elif score == total_possible:
        status = "PASSED"
        score_value = score
    elif score > 0:
        status = "PARTIAL"
        score_value = score
    else:
        status = "FAILED"
        score_value = score
    return GradingResult(task_id, task_revision, status, True, score_value, tuple(results), ())


def grade_task(task: TaskDefinition, observations: list[dict[str, Any]]) -> GradingResult:
    group_definitions = {
        group.id: (group.dimension, group.max_score) for group in task.test_manifest.public_groups
    }
    return grade_observations(task.task_id, task.revision, observations, group_definitions)
