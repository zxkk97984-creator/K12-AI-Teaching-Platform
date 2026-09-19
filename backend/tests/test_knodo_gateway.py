"""T10: the four fixed operations, schema enforcement and honest fixture modes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.integrations.knodo import (
    DESIGNER_OPERATIONS,
    OPERATION_SPECS,
    TUTOR_OPERATIONS,
    GatewayStatus,
    Operation,
    build_gateway,
)
from app.integrations.knodo.fixture import FixtureScenario

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


REQUEST_EXAMPLES = {
    Operation.TEACH_TURN: "teaching-request",
    Operation.CODE_FEEDBACK: "teaching-request",
    Operation.QUIZ_DRAFT: "designer-request",
    Operation.LESSON_PACKAGE_DRAFT: "designer-package-request",
}


def make_settings(**overrides) -> Settings:
    base = {
        "app_env": "test",
        "app_session_secret": "t" * 40,
        "test_database_url": "postgresql+asyncpg://u:p@127.0.0.1:55434/k12r1_test",
        "database_url": "postgresql+asyncpg://u:p@127.0.0.1:55433/k12r1_dev",
        "allowed_origins": "http://127.0.0.1:15173",
        "gateway_mode": "fixture",
        "gateway_timeout_seconds": 2,
    }
    base.update(overrides)
    return Settings(**base)


def request_for(operation: Operation) -> dict:
    payload = load_example(REQUEST_EXAMPLES[operation])
    if operation is Operation.CODE_FEEDBACK:
        payload["operation"] = "CODE_FEEDBACK"
        payload["event"] = "CODE_RUN_COMPLETED"
        payload["current_phase"] = "PRACTICE"
        payload["code_feedback_facts"] = {
            "run_id": "synthetic-run-1",
            "task_id": "synthetic-task-1",
            "code_hash": "sha256:synthetic",
            "code_excerpt": "print(1)",
            "execution_status": "SUCCEEDED",
            "correctness_status": "PASSED",
            "stdout_excerpt": "1",
            "error_excerpt": "",
            "passed_cases": 2,
            "total_cases": 2,
        }
    return payload


def test_operation_roles_are_fixed() -> None:
    assert set(OPERATION_SPECS) == {
        Operation.TEACH_TURN,
        Operation.CODE_FEEDBACK,
        Operation.QUIZ_DRAFT,
        Operation.LESSON_PACKAGE_DRAFT,
    }
    assert TUTOR_OPERATIONS == {Operation.TEACH_TURN, Operation.CODE_FEEDBACK}
    assert DESIGNER_OPERATIONS == {Operation.QUIZ_DRAFT, Operation.LESSON_PACKAGE_DRAFT}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", list(Operation))
async def test_each_operation_has_a_positive_fixture_case(operation: Operation) -> None:
    gateway = build_gateway(make_settings())
    result = await gateway.invoke(operation.value, request_for(operation))
    assert result.status is GatewayStatus.OK, result.error
    assert result.operation is operation
    assert result.fixture is True
    assert result.fixture_notice == "SYNTHETIC_FIXTURE_FOR_DEV_TEST_ONLY_NOT_A_REAL_SAMPLE"
    assert gateway.registry.validate_response(operation, result.output) == []
    assert result.usage.output_bytes == len(
        json.dumps(result.output, ensure_ascii=False).encode("utf-8")
    )


@pytest.mark.asyncio
async def test_unknown_operation_fails_closed_without_calling_backend() -> None:
    gateway = build_gateway(make_settings())
    result = await gateway.invoke("DELETE_EVERYTHING", request_for(Operation.TEACH_TURN))
    assert result.status is GatewayStatus.FAILED
    assert result.error is not None
    assert result.error.category.value == "UNSUPPORTED_OPERATION"
    assert result.error.reason_code == "UNKNOWN_OPERATION"
    assert result.output is None
    assert result.usage.upstream_calls == 0


@pytest.mark.asyncio
async def test_unknown_operation_is_not_echoed_in_public_error() -> None:
    gateway = build_gateway(make_settings())
    marker = "AKIAABCDEFGHIJKLMNOP"
    result = await gateway.invoke(marker, request_for(Operation.TEACH_TURN))
    assert result.error is not None
    assert marker not in result.model_dump_json()


@pytest.mark.asyncio
async def test_request_schema_mismatch_is_rejected_without_echoing_input() -> None:
    gateway = build_gateway(make_settings())
    base = request_for(Operation.TEACH_TURN)
    mutations = {
        "extra_property": {**base, "totally_unknown": "sentinel-value-1234"},
        "wrong_type": {**base, "base_revision": "1"},
        "unknown_enum": {**base, "event": "TELEPORT"},
        "missing_required": {key: value for key, value in base.items() if key != "learner"},
        "bad_grade": {**base, "learner": {**base["learner"], "grade": 13}},
        "bool_grade": {**base, "learner": {**base["learner"], "grade": True}},
    }
    for label, payload in mutations.items():
        result = await gateway.invoke(Operation.TEACH_TURN.value, payload)
        assert result.status is GatewayStatus.FAILED, label
        assert result.error is not None and result.error.category.value == "VALIDATION", label
        assert result.output is None, label
        if label == "extra_property":
            assert "sentinel-value-1234" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_nullable_grade_still_allowed() -> None:
    gateway = build_gateway(make_settings())
    payload = request_for(Operation.TEACH_TURN)
    payload["learner"] = {**payload["learner"], "grade": None}
    result = await gateway.invoke(Operation.TEACH_TURN.value, payload)
    assert result.status is GatewayStatus.OK


@pytest.mark.asyncio
async def test_designer_operation_branch_is_enforced() -> None:
    gateway = build_gateway(make_settings())
    quiz = request_for(Operation.QUIZ_DRAFT)
    # A *valid* lesson_spec on a QUIZ_DRAFT request: only the operation branch rejects it.
    valid_lesson_spec = load_example("designer-package-request")["lesson_spec"]
    swapped = {**quiz, "operation": "QUIZ_DRAFT", "lesson_spec": valid_lesson_spec}
    result = await gateway.invoke(Operation.QUIZ_DRAFT.value, swapped)
    assert result.status is GatewayStatus.FAILED
    assert result.error is not None and result.error.category.value == "VALIDATION"

    lesson = request_for(Operation.LESSON_PACKAGE_DRAFT)
    wrong_branch = {
        **lesson,
        "quiz_spec": {
            "count": 1,
            "difficulty": "EASY",
            "question_types": ["SINGLE_CHOICE"],
            "misconception_summary": "",
        },
    }
    result = await gateway.invoke(Operation.LESSON_PACKAGE_DRAFT.value, wrong_branch)
    assert result.status is GatewayStatus.FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "category"),
    [
        (FixtureScenario.AUTH_401, "AUTH"),
        (FixtureScenario.AUTH_403, "AUTH"),
        (FixtureScenario.RATE_429, "RATE"),
        (FixtureScenario.SERVER_500, "SERVER"),
        (FixtureScenario.MALFORMED_JSON, "VALIDATION"),
        (FixtureScenario.OUTPUT_OVER_LIMIT, "OUTPUT_LIMIT"),
    ],
)
async def test_failure_scenarios_map_to_the_taxonomy(
    scenario: FixtureScenario, category: str
) -> None:
    gateway = build_gateway(make_settings())
    result = await gateway.invoke(
        Operation.TEACH_TURN.value, request_for(Operation.TEACH_TURN), scenario=scenario
    )
    assert result.status is GatewayStatus.FAILED
    assert result.error is not None and result.error.category.value == category
    assert result.output is None


@pytest.mark.asyncio
async def test_insufficient_evidence_is_a_first_class_status() -> None:
    gateway = build_gateway(make_settings())
    result = await gateway.invoke(
        Operation.TEACH_TURN.value,
        request_for(Operation.TEACH_TURN),
        scenario=FixtureScenario.INSUFFICIENT_EVIDENCE,
    )
    assert result.status is GatewayStatus.INSUFFICIENT_EVIDENCE
    assert result.output is not None
    assert "INSUFFICIENT_SOURCE" in result.output["warnings"]


@pytest.mark.asyncio
async def test_delay_timeout_and_cancel_are_predictable() -> None:
    gateway = build_gateway(make_settings())
    request = request_for(Operation.TEACH_TURN)

    slow = await gateway.invoke(
        Operation.TEACH_TURN.value, request, scenario=FixtureScenario.DELAY, delay_seconds=0.2
    )
    assert slow.status is GatewayStatus.OK
    assert slow.usage.duration_ms >= 150

    timed_out = await gateway.invoke(
        Operation.TEACH_TURN.value,
        request,
        scenario=FixtureScenario.DELAY,
        delay_seconds=1.0,
        timeout_seconds=0.1,
    )
    assert timed_out.status is GatewayStatus.FAILED
    assert timed_out.error is not None and timed_out.error.category.value == "TIMEOUT"

    cancel = asyncio.Event()

    async def signal_cancel() -> None:
        await asyncio.sleep(0.05)
        cancel.set()

    canceller = asyncio.create_task(signal_cancel())
    cancelled = await gateway.invoke(
        Operation.TEACH_TURN.value,
        request,
        scenario=FixtureScenario.CANCEL,
        delay_seconds=2.0,
        cancel=cancel,
    )
    await canceller
    assert cancelled.status is GatewayStatus.CANCELLED
    assert cancelled.output is None
    assert cancelled.error is not None and cancelled.error.category.value == "CANCEL"


@pytest.mark.asyncio
async def test_status_endpoint_reports_the_mode_honestly(client, app) -> None:
    gateway = build_gateway(make_settings(gateway_mode="disabled"))
    app.state.gateway = gateway
    response = await client.get("/api/v1/ai/gateway/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "disabled"
    assert body["available"] is False
    assert body["reason_code"] == "GATEWAY_DISABLED"
    assert body["fixture"] is False
    assert [item["id"] for item in body["operations"]] == [op.value for op in Operation]
    assert "http" not in response.text
    assert "token" not in response.text.lower()
