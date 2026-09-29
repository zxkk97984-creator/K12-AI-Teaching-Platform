from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from runner.host.runner import ContainerResult, RunRequest

from app.integrations.knodo.fixture import FixtureGateway
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.modules.codelab.feedback import (
    FeedbackSnapshotError,
    StaleFeedbackError,
    build_feedback_request,
    build_run_snapshot,
    feedback_idempotency_key,
    public_code_run_projection,
    validate_feedback,
)
from app.modules.codelab.grading import GradingResult, GroupResult, grade_observations
from app.modules.codelab.router import (
    _code_feedback_request,
    _code_feedback_validation_context,
    _run_view,
    _snapshot_for_run,
)
from app.modules.teaching.validation import validate_assistant_output


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


def test_code_feedback_request_is_schema_valid_and_task_scoped() -> None:
    run = SimpleNamespace(id=uuid.uuid4())
    task = SimpleNamespace(
        task_id="temperature-converter",
        revision=1,
        title="温度转换",
        description="把摄氏温度转换为华氏温度。",
        chapter_binding={
            "chapter_slug": "ai-python-basics",
            "stage": "JUNIOR",
            "knowledge_point_slugs": ["functions"],
        },
    )
    request = _code_feedback_request(run=run, task=task)
    assert default_registry().validate_request(Operation.CODE_FEEDBACK, request) == []
    assert request["allowed_code_task_ids"] == ["temperature-converter"]
    assert request["allowed_actions"] == []
    assert request["code_feedback_facts"] is None


def test_code_feedback_may_cite_only_its_trusted_task_source() -> None:
    run = SimpleNamespace(id=uuid.uuid4())
    task = SimpleNamespace(
        task_id="temperature-converter",
        revision=1,
        title="温度转换",
        description="把摄氏温度转换为华氏温度。",
        chapter_binding={
            "chapter_slug": "ai-python-basics",
            "stage": "JUNIOR",
            "knowledge_point_slugs": ["functions"],
        },
    )
    request = _code_feedback_request(run=run, task=task)
    payload = {
        "schema_version": "k12.teaching.response.v1",
        "request_id": request["request_id"],
        "lesson_session_id": request["lesson_session_id"],
        "base_revision": 0,
        "curriculum_revision": request["curriculum_revision"],
        "message_markdown": "测试通过，可继续检查边界输入。",
        "source_refs": [
            {
                "source_id": "codelab-task:temperature-converter",
                "revision": "1",
                "locator": "task.description",
            }
        ],
        "evidence_refs": [],
        "followup_question": None,
        "action": None,
        "phase_suggestion": None,
        "warnings": [],
    }
    assert (
        validate_assistant_output(
            operation=Operation.CODE_FEEDBACK,
            payload=payload,
            context=_code_feedback_validation_context(request),
            fixture_allowance=None,
        )
        == []
    )
    payload["source_refs"][0]["source_id"] = "untrusted-source"
    assert "SOURCE_NOT_ALLOWED" in validate_assistant_output(
        operation=Operation.CODE_FEEDBACK,
        payload=payload,
        context=_code_feedback_validation_context(request),
        fixture_allowance=None,
    )


def test_persisted_runner_observations_rebuild_a_trusted_feedback_snapshot() -> None:
    code = "def celsius_to_fahrenheit(celsius):\n    return celsius * 9 / 5 + 32\n"
    outputs = {
        "f1-freezing": 32,
        "f1-boiling": 212,
        "f1-body": 98.6,
        "f2-below-zero": 14,
        "f2-minus-forty": -40,
        "f2-decimal": 97.88,
        "r1-number": 68,
        "r1-decimal-number": 32.9,
    }
    raw_observations = [
        {
            "case_id": case_id,
            "execution_status": "COMPLETED",
            "actual_output": output,
            "stdout": "",
            "stderr": "",
        }
        for case_id, output in outputs.items()
    ]
    trusted_grade = grade_observations("temperature-converter", 1, raw_observations)
    run = SimpleNamespace(
        id=uuid.uuid4(),
        purpose="GRADE",
        result={
            "grading": trusted_grade.as_dict(),
            "observations": [
                {"case_id": item["case_id"], "execution_status": item["execution_status"]}
                for item in raw_observations
            ],
        },
        execution_status="SUCCEEDED",
        correctness_status=trusted_grade.status,
        deterministic_score=trusted_grade.deterministic_score,
        code=code,
        code_sha256=hashlib.sha256(code.encode()).hexdigest(),
    )
    task = SimpleNamespace(
        task_id="temperature-converter",
        revision=1,
        title="温度转换",
        description="把摄氏温度转换为华氏温度。",
        entrypoint="celsius_to_fahrenheit",
        chapter_binding={
            "chapter_slug": "ai-python-basics",
            "stage": "JUNIOR",
            "knowledge_point_slugs": ["functions"],
        },
        test_manifest={
            "public_groups": [
                {"id": "F1", "dimension": "F", "max_score": 30},
                {"id": "F2", "dimension": "F", "max_score": 30},
                {"id": "R1", "dimension": "R", "max_score": 10},
            ]
        },
    )
    snapshot = _snapshot_for_run(run=run, task=task, owner_id="student-a")
    assert snapshot.correctness_status == "PASSED"
    assert snapshot.deterministic_score == 70
    assert snapshot.passed_cases == 8
    assert snapshot.total_cases == 8
    feedback_request = _teaching_request()
    feedback_request["operation"] = "CODE_FEEDBACK"
    feedback_request["allowed_code_task_ids"] = [snapshot.task_id]
    facts = build_feedback_request(feedback_request, snapshot, authenticated_owner_id="student-a")[
        "code_feedback_facts"
    ]
    assert facts["correctness_status"] == "PASSED"
    assert facts["passed_cases"] == 8
    assert facts["total_cases"] == 8
    run.correctness_status = "FAILED"
    with pytest.raises(FeedbackSnapshotError, match="persisted grade"):
        _snapshot_for_run(run=run, task=task, owner_id="student-a")
    run.correctness_status = "PASSED"
    request = build_feedback_request(
        _code_feedback_request(run=run, task=task),
        snapshot,
        authenticated_owner_id="student-a",
    )
    assert request["code_feedback_facts"]["code_hash"] == run.code_sha256


def test_old_feedback_with_incomplete_grading_facts_is_hidden_until_regenerated() -> None:
    run = SimpleNamespace(
        id=uuid.uuid4(),
        task_id="temperature-converter",
        task_revision=1,
        lesson_session_id=None,
        scope_key=None,
        purpose="GRADE",
        quiz_session_id=None,
        question_id=None,
        status="SUCCEEDED",
        execution_status="SUCCEEDED",
        correctness_status="PASSED",
        deterministic_score=70,
        code_sha256="0" * 64,
        code="def celsius_to_fahrenheit(celsius):\n    return celsius * 9 / 5 + 32\n",
        result=None,
        feedback_status="READY",
        feedback={"status": "READY", "summary": "错误地说 0/8 失败", "references": []},
        created_at=None,
        completed_at=None,
    )
    projected = _run_view(run)
    assert projected["feedback_status"] == "STALE"
    assert "0/8" not in json.dumps(projected, ensure_ascii=False, default=str)
    assert projected["correctness_status"] == "PASSED"
    assert projected["deterministic_score"] == 70
