from __future__ import annotations

from app.modules.codelab.contracts import load_catalog
from app.modules.codelab.grading import grade_observations, grade_task
from app.modules.codelab.trusted import expected_output, trusted_cases


def _correct_observations(task_id: str) -> list[dict]:
    return [
        {
            "case_id": case.case_id,
            "execution_status": "COMPLETED",
            "actual_output": expected_output(task_id, case.input),
        }
        for case in trusted_cases(task_id)
    ]


def test_all_three_reference_oracles_cover_every_trusted_case() -> None:
    for task_id in ("temperature-converter", "list-summary", "binary-search"):
        result = grade_observations(task_id, 1, _correct_observations(task_id))
        assert result.status == "PASSED"
        assert result.deterministic_score == 70.0
        assert sum(group.passed for group in result.groups) == len(trusted_cases(task_id))


def test_wrong_structured_output_is_failed_even_with_fake_success_stdout() -> None:
    observations = _correct_observations("binary-search")
    observations[0]["actual_output"] = -1
    observations[0]["stdout"] = "SUCCESS: 8/8 passed"
    observations[0]["reported_passed"] = 8
    result = grade_observations("binary-search", 1, observations)
    assert result.status == "PARTIAL"
    assert result.deterministic_score is not None and result.deterministic_score < 70


def test_missing_tests_is_not_verified_and_has_no_authoritative_score() -> None:
    result = grade_observations("temperature-converter", 1, [])
    assert result.status == "NOT_VERIFIED"
    assert result.deterministic_score is None


def test_runner_system_error_is_not_student_zero() -> None:
    observations = _correct_observations("list-summary")
    observations[0] = {"case_id": observations[0]["case_id"], "execution_status": "RUNNER_ERROR"}
    result = grade_observations("list-summary", 1, observations)
    assert result.status == "SYSTEM_ERROR"
    assert result.deterministic_score is None


def test_student_exception_is_a_failed_case_not_a_fake_system_pass() -> None:
    observations = _correct_observations("temperature-converter")
    observations[0] = {
        "case_id": observations[0]["case_id"],
        "execution_status": "STUDENT_EXCEPTION",
        "stdout": "all tests passed",
    }
    result = grade_observations("temperature-converter", 1, observations)
    assert result.status == "PARTIAL"
    assert result.groups[0].failed == 1


def test_unknown_runner_status_is_a_system_error() -> None:
    observation = {
        "case_id": trusted_cases("list-summary")[0].case_id,
        "execution_status": "SUCCESS",
    }
    result = grade_observations("list-summary", 1, [observation])
    assert result.status == "SYSTEM_ERROR"
    assert result.deterministic_score is None


def test_grade_task_uses_manifest_group_definitions() -> None:
    task = next(task for _, task in load_catalog() if task.task_id == "binary-search")
    result = grade_task(task, _correct_observations(task.task_id))
    assert result.status == "PASSED"
