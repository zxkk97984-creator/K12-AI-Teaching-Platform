from __future__ import annotations

import json
from pathlib import Path

import pytest
from runner.host.runner import ContainerResult, RunRequest

from app.integrations.knodo.fixture import FixtureGateway
from app.integrations.knodo.operations import Operation
from app.modules.codelab.feedback import (
    FeedbackSnapshotError,
    StaleFeedbackError,
    build_feedback_request,
    build_run_snapshot,
    feedback_idempotency_key,
    public_code_run_projection,
    validate_feedback,
)
from app.modules.codelab.grading import GradingResult, GroupResult


def _request(*, code: str = "def celsius_to_fahrenheit(celsius):\n    return 32\n") -> RunRequest:
    return RunRequest.from_payload(
        {
            "case_id": "feedback-case",
            "task_id": "temperature-converter",
            "task_revision": 1,
            "entrypoint": "celsius_to_fahrenheit",
            "input": {"celsius": 0},
            "student_code": code,
            "owner_id": "student-a",
            "lease_id": "lease-a",
        }
    )


def _grade(status: str = "PASSED", score: float | None = 70.0) -> GradingResult:
    passed = 3 if status == "PASSED" else 0
    return GradingResult(
        task_id="temperature-converter",
        task_revision=1,
        status=status,
        deterministic_tests_available=status != "NOT_VERIFIED",
        deterministic_score=score,
        groups=(
            GroupResult("F1", "F", 30, passed, 3 - passed, 0, 30 if passed else 0),
            GroupResult("F2", "F", 30, 0, 3, 0, 0),
            GroupResult("R1", "R", 10, 0, 2, 0, 0),
        ),
    )


def _snapshot(*, grade_status: str = "PASSED", score: float | None = 70.0, code: str | None = None):
    request = _request(code=code or "def celsius_to_fahrenheit(celsius):\n    return 32\n")
    result = ContainerResult(
        case_id=request.case_id,
        execution_status="COMPLETED",
        actual_output=32,
        student_stdout="SUCCESS: all tests passed\n",
        code_sha256=request.code_sha256,
    )
    return request, build_run_snapshot(
        owner_id="student-a",
        run_id="run-1",
        request=request,
        result=result,
        grade=_grade(grade_status, score),
    )


def _teaching_request() -> dict:
    return json.loads(
        (
            Path(__file__).resolve().parents[2] / "contracts/examples/teaching-request.json"
        ).read_text(encoding="utf-8")
    )


def test_feedback_request_contains_only_current_run_facts() -> None:
    _, snapshot = _snapshot()
    request = _teaching_request()
    request["operation"] = "CODE_FEEDBACK"
    request["allowed_code_task_ids"] = [snapshot.task_id]
    payload = build_feedback_request(request, snapshot, authenticated_owner_id="student-a")
    assert payload["code_feedback_facts"]["run_id"] == "run-1"
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "reference_solution" not in dumped
    assert "hidden_tests" not in dumped
    assert "passed=100" not in dumped


@pytest.mark.asyncio
async def test_fixture_code_feedback_is_offline_and_explicitly_not_real_knodo() -> None:
    _, snapshot = _snapshot()
    request = _teaching_request()
    request["operation"] = "CODE_FEEDBACK"
    request["allowed_code_task_ids"] = [snapshot.task_id]
    payload = build_feedback_request(request, snapshot, authenticated_owner_id="student-a")
    outcome = await FixtureGateway(max_output_bytes=262_144, default_timeout_seconds=2).invoke(
        Operation.CODE_FEEDBACK, payload
    )
    assert outcome.error is None
    assert "合成代码反馈样例" in outcome.payload["message_markdown"]


def test_ai_cannot_replace_failed_deterministic_result_or_add_score() -> None:
    _, snapshot = _snapshot(grade_status="FAILED", score=0.0)
    feedback = validate_feedback(
        {
            "status": "READY",
            "run_id": snapshot.run_id,
            "code_hash": snapshot.code_hash,
            "summary": "AI声称全过，但这不是可信判定。",
            "references": [],
        },
        snapshot,
    )
    projection = public_code_run_projection(snapshot, feedback)
    assert projection["correctness_status"] == "FAILED"
    assert projection["deterministic_score"] == 0.0
    assert projection["ai_feedback_status"] == "READY"


def test_ai_unavailable_does_not_fill_a_zero_or_hide_real_result() -> None:
    _, snapshot = _snapshot(grade_status="PASSED", score=70.0)
    projection = public_code_run_projection(snapshot)
    assert projection["ai_feedback_status"] == "UNAVAILABLE"
    assert projection["deterministic_score"] == 70.0


def test_feedback_line_reference_and_snapshot_hash_are_checked() -> None:
    _, snapshot = _snapshot()
    with pytest.raises(StaleFeedbackError, match="line"):
        validate_feedback(
            {
                "status": "READY",
                "run_id": snapshot.run_id,
                "code_hash": snapshot.code_hash,
                "summary": "越界引用",
                "references": [{"line": 99, "kind": "ERROR", "message": "bad"}],
            },
            snapshot,
        )
    with pytest.raises(StaleFeedbackError, match="another run"):
        validate_feedback(
            {
                "status": "READY",
                "run_id": "other-run",
                "code_hash": snapshot.code_hash,
                "summary": "旧反馈",
                "references": [],
            },
            snapshot,
        )


def test_editing_code_changes_idempotency_key_and_rejects_old_feedback() -> None:
    first_request, first = _snapshot()
    second_request, second = _snapshot(code="def celsius_to_fahrenheit(celsius):\n    return 0\n")
    assert first.code_hash != second.code_hash
    assert feedback_idempotency_key(
        owner_id="student-a", run_id="run-1", code_hash=first.code_hash
    ) != feedback_idempotency_key(owner_id="student-a", run_id="run-1", code_hash=second.code_hash)
    with pytest.raises(StaleFeedbackError):
        validate_feedback(
            {
                "status": "READY",
                "run_id": "run-1",
                "code_hash": first.code_hash,
                "summary": "旧代码反馈",
                "references": [],
            },
            second,
        )
    assert first_request.code_sha256 != second_request.code_sha256


def test_feedback_owner_is_checked_before_building_tutor_request() -> None:
    _, snapshot = _snapshot()
    request = _teaching_request()
    request["operation"] = "CODE_FEEDBACK"
    request["allowed_code_task_ids"] = [snapshot.task_id]
    with pytest.raises(FeedbackSnapshotError, match="owner"):
        build_feedback_request(request, snapshot, authenticated_owner_id="student-b")
