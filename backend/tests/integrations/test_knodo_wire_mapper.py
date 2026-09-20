"""T11: evidence-backed Knodo Bot Chat wire mapping.

These tests use a recording transport. They verify the official request and
response shape without making a network request or claiming tenant validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.integrations.knodo.budget import FileRequestBudget
from app.integrations.knodo.gateway import AgentGateway
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.integrations.knodo.types import BackendOutcome
from app.integrations.knodo.wire import (
    InMemoryRequestBudget,
    KnodoTarget,
    KnodoWireMapper,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "contracts" / "examples"
SYNTHETIC_PAT = "jvs_synthetic_test_value_not_a_real_credential"


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def completion(content: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "chatcmpl-synthetic-001",
        "object": "chat.completion",
        "created": 1_790_000_000,
        "model": "tenant-configured-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33},
        "conversationId": "conv_synthetic_001",
    }
    payload.update(overrides)
    return payload


class RecordingTransport:
    def __init__(self, outcome: BackendOutcome):
        self.outcome = outcome
        self.requests = []

    async def send(self, request, *, timeout_seconds: float, cancel=None) -> BackendOutcome:
        self.requests.append((request, timeout_seconds, cancel))
        return self.outcome


def mapper(
    outcome: BackendOutcome,
    *,
    budget: InMemoryRequestBudget | None = None,
) -> tuple[KnodoWireMapper, RecordingTransport]:
    transport = RecordingTransport(outcome)
    value = KnodoWireMapper(
        base_url="https://knodo.example.invalid",
        token=SYNTHETIC_PAT,
        targets={
            "tutor": KnodoTarget(
                bot_id="tutor-bot-synthetic",
                workspace_id="tutor-workspace-synthetic",
            ),
            "designer": KnodoTarget(
                bot_id="designer-bot-synthetic",
                workspace_id="designer-workspace-synthetic",
            ),
        },
        transport=transport,
        budget=budget or InMemoryRequestBudget(20),
    )
    return value, transport


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "request_example", "response_example", "expected_bot"),
    [
        (Operation.TEACH_TURN, "teaching-request", "teaching-response", "tutor-bot-synthetic"),
        (Operation.QUIZ_DRAFT, "designer-request", "quiz-draft", "designer-bot-synthetic"),
    ],
)
async def test_first_turn_maps_only_documented_fields_and_fixed_role_target(
    operation: Operation,
    request_example: str,
    response_example: str,
    expected_bot: str,
) -> None:
    local_request = example(request_example)
    upstream = completion(example(response_example))
    value, transport = mapper(BackendOutcome(payload=upstream, upstream_calls=1))

    outcome = await value.invoke(operation, local_request, timeout_seconds=7)

    assert outcome.error is None
    assert outcome.payload == example(response_example)
    assert len(transport.requests) == 1
    sent, timeout, _ = transport.requests[0]
    assert sent.url == (
        f"https://knodo.example.invalid/api/v1/bots/{expected_bot}/chat/completions"
    )
    assert sent.headers == {
        "Authorization": f"Bearer {SYNTHETIC_PAT}",
        "Content-Type": "application/json",
    }
    assert timeout == 7
    assert sent.payload == {
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    local_request,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        ],
        "stream": False,
        "permissionMode": "default",
        "includeToolResults": False,
    }
    assert "model" not in sent.payload
    assert "conversationId" not in sent.payload


@pytest.mark.asyncio
async def test_continue_turn_uses_only_backend_supplied_conversation_id() -> None:
    local_request = example("teaching-request")
    local_request["conversationId"] = "student-controlled-value-must-not-be-used"
    value, transport = mapper(
        BackendOutcome(
            payload=completion(
                example("teaching-response"),
                conversationId="conv_backend_owned_002",
            ),
            upstream_calls=1,
        )
    )

    outcome = await value.invoke(
        Operation.TEACH_TURN,
        local_request,
        timeout_seconds=5,
        remote_conversation_id="conv_backend_owned_002",
    )

    assert outcome.error is None
    sent = transport.requests[0][0]
    assert sent.payload["conversationId"] == "conv_backend_owned_002"
    encoded_local_request = json.loads(sent.payload["messages"][0]["content"])
    assert encoded_local_request["conversationId"] == "student-controlled-value-must-not-be-used"


@pytest.mark.asyncio
async def test_continuation_rejects_a_mismatched_response_conversation() -> None:
    value, _ = mapper(
        BackendOutcome(
            payload=completion(example("teaching-response")),
            upstream_calls=1,
        )
    )

    outcome = await value.invoke(
        Operation.TEACH_TURN,
        example("teaching-request"),
        timeout_seconds=5,
        remote_conversation_id="conv_backend_owned_002",
    )

    assert outcome.payload is None
    assert outcome.error is not None
    assert outcome.error.reason_code == "KNODO_CONVERSATION_MISMATCH"


@pytest.mark.asyncio
async def test_conversation_id_is_treated_as_opaque_documented_string() -> None:
    opaque_id = "conv:synthetic/opaque.value"
    value, transport = mapper(
        BackendOutcome(
            payload=completion(
                example("teaching-response"),
                conversationId=opaque_id,
            ),
            upstream_calls=1,
        )
    )

    outcome = await value.invoke(
        Operation.TEACH_TURN,
        example("teaching-request"),
        timeout_seconds=5,
        remote_conversation_id=opaque_id,
    )

    assert outcome.error is None
    assert transport.requests[0][0].payload["conversationId"] == opaque_id


@pytest.mark.asyncio
async def test_response_extracts_minimal_non_secret_remote_metadata() -> None:
    value, _ = mapper(
        BackendOutcome(
            payload=completion(example("teaching-response")),
            upstream_calls=1,
        )
    )

    outcome = await value.invoke(
        Operation.TEACH_TURN,
        example("teaching-request"),
        timeout_seconds=5,
    )

    assert outcome.remote_metadata == {
        "provider": "knodo",
        "role": "tutor",
        "bot_id": "tutor-bot-synthetic",
        "workspace_id": "tutor-workspace-synthetic",
        "completion_id": "chatcmpl-synthetic-001",
        "conversation_id": "conv_synthetic_001",
        "model": "tenant-configured-model",
        "finish_reason": "stop",
        "prompt_tokens": 11,
        "completion_tokens": 22,
        "total_tokens": 33,
    }
    assert SYNTHETIC_PAT not in json.dumps(outcome.remote_metadata)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wire_payload", "reason"),
    [
        ({}, "KNODO_RESPONSE_SHAPE_INVALID"),
        (
            completion(example("teaching-response"), choices=[]),
            "KNODO_RESPONSE_SHAPE_INVALID",
        ),
        (
            completion(
                example("teaching-response"),
                choices=[
                    {
                        "index": 0,
                        "message": {"role": "user", "content": "{}"},
                        "finish_reason": "stop",
                    }
                ],
            ),
            "KNODO_RESPONSE_SHAPE_INVALID",
        ),
        (
            completion(
                example("teaching-response"),
                choices=[
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "说明文字\n{}",
                        },
                        "finish_reason": "stop",
                    }
                ],
            ),
            "KNODO_ASSISTANT_CONTENT_NOT_JSON_OBJECT",
        ),
        (
            completion(
                example("teaching-response"),
                choices=[
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "length",
                    }
                ],
            ),
            "KNODO_RESPONSE_INCOMPLETE",
        ),
    ],
)
async def test_http_200_business_or_shape_failures_are_not_success(
    wire_payload: dict[str, Any], reason: str
) -> None:
    value, _ = mapper(BackendOutcome(payload=wire_payload, upstream_calls=1))

    outcome = await value.invoke(
        Operation.TEACH_TURN,
        example("teaching-request"),
        timeout_seconds=5,
    )

    assert outcome.payload is None
    assert outcome.error is not None
    assert outcome.error.reason_code == reason
    assert outcome.upstream_calls == 1


@pytest.mark.asyncio
async def test_invalid_assistant_content_preserves_remote_conversation_metadata() -> None:
    wire_payload = completion(
        example("teaching-response"),
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": "not-json"},
                "finish_reason": "stop",
            }
        ],
    )
    value, _ = mapper(BackendOutcome(payload=wire_payload, upstream_calls=1))

    outcome = await value.invoke(
        Operation.TEACH_TURN,
        example("teaching-request"),
        timeout_seconds=5,
    )

    assert outcome.error is not None
    assert outcome.remote_metadata is not None
    assert outcome.remote_metadata["conversation_id"] == "conv_synthetic_001"


@pytest.mark.asyncio
async def test_gateway_failure_preserves_metadata_needed_to_avoid_orphaned_conversation() -> None:
    metadata = {
        "provider": "knodo",
        "conversation_id": "conv_synthetic_accepted_but_invalid",
    }

    class InvalidSemanticBackend:
        async def invoke(self, operation, request, **kwargs):
            return BackendOutcome(
                payload={"not": "a teaching response"},
                upstream_calls=1,
                remote_metadata=metadata,
            )

    gateway = AgentGateway(
        mode="knodo",
        registry=default_registry(),
        backend=InvalidSemanticBackend(),  # type: ignore[arg-type]
        timeout_seconds=5,
        max_output_bytes=262_144,
    )

    result = await gateway.invoke(Operation.TEACH_TURN, example("teaching-request"))

    assert result.status.value == "FAILED"
    assert result.error is not None
    assert result.error.reason_code == "RESPONSE_SCHEMA_MISMATCH"
    assert result.remote_metadata == metadata


@pytest.mark.asyncio
async def test_budget_is_reserved_before_send_and_exhaustion_is_fail_closed() -> None:
    budget = InMemoryRequestBudget(1)
    value, transport = mapper(
        BackendOutcome(
            payload=completion(example("teaching-response")),
            upstream_calls=1,
        ),
        budget=budget,
    )

    first = await value.invoke(
        Operation.TEACH_TURN,
        example("teaching-request"),
        timeout_seconds=5,
    )
    second = await value.invoke(
        Operation.TEACH_TURN,
        example("teaching-request"),
        timeout_seconds=5,
    )

    assert first.error is None
    assert second.error is not None
    assert second.error.reason_code == "LIVE_REQUEST_BUDGET_EXHAUSTED"
    assert second.upstream_calls == 0
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "bad_value",
    [
        "https://knodo.example.invalid/path",
        "https://user@knodo.example.invalid",
        "https://knodo.example.invalid?query=1",
        "ftp://knodo.example.invalid",
        "http://knodo.example.invalid",
    ],
)
def test_mapper_rejects_unsafe_or_non_origin_base_urls(bad_value: str) -> None:
    with pytest.raises(ValueError):
        KnodoWireMapper(
            base_url=bad_value,
            token=SYNTHETIC_PAT,
            targets={
                "tutor": KnodoTarget("tutor-bot-synthetic", "tutor-workspace-synthetic"),
                "designer": KnodoTarget("designer-bot-synthetic", "designer-workspace-synthetic"),
            },
            transport=RecordingTransport(BackendOutcome(payload={})),
            budget=InMemoryRequestBudget(1),
        )


def test_continuation_scope_is_server_owned_and_invalidates_on_target_change() -> None:
    value, _ = mapper(BackendOutcome(payload={}))

    teach_scope = value.continuation_scope(Operation.TEACH_TURN, contract_version="1.0.0")
    code_scope = value.continuation_scope(Operation.CODE_FEEDBACK, contract_version="1.0.0")
    designer_scope = value.continuation_scope(Operation.QUIZ_DRAFT, contract_version="1.0.0")

    assert teach_scope == code_scope
    assert teach_scope != designer_scope
    assert "tutor-bot-synthetic" in teach_scope
    assert "tutor-workspace-synthetic" in teach_scope
    assert SYNTHETIC_PAT not in teach_scope

    changed_target, _ = mapper(BackendOutcome(payload={}))
    changed_target._targets["tutor"] = KnodoTarget(  # type: ignore[index]
        bot_id="replacement-tutor-bot",
        workspace_id="tutor-workspace-synthetic",
    )
    assert (
        changed_target.continuation_scope(Operation.TEACH_TURN, contract_version="1.0.0")
        != teach_scope
    )


def test_agent_gateway_exposes_no_continuation_scope_for_fixture() -> None:
    gateway = AgentGateway(
        mode="fixture",
        registry=default_registry(),
        backend=None,
        timeout_seconds=5,
        max_output_bytes=262_144,
        unavailable_reason="synthetic",
    )

    assert gateway.continuation_scope(Operation.TEACH_TURN) is None


@pytest.mark.asyncio
async def test_file_budget_is_shared_across_instances_and_cannot_auto_expand(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "private" / "knodo-budget.json"
    first_process = FileRequestBudget(ledger, max_requests=2)
    second_process = FileRequestBudget(ledger, max_requests=2)

    assert await first_process.reserve() is True
    assert await second_process.reserve() is True
    assert await first_process.reserve() is False

    persisted = json.loads(ledger.read_text(encoding="utf-8"))
    assert persisted == {
        "schema_version": "k12.knodo.request-budget.v1",
        "authorized_max_requests": 2,
        "reserved_requests": 2,
    }
    assert ledger.stat().st_mode & 0o077 == 0

    # Raising an environment/configured cap must not silently expand a ledger
    # that was already authorised at a lower value.
    attempted_expansion = FileRequestBudget(ledger, max_requests=20)
    assert await attempted_expansion.reserve() is False


@pytest.mark.asyncio
async def test_file_budget_persists_a_tighter_cap_even_when_already_exhausted(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "budget.json"
    assert await FileRequestBudget(ledger, max_requests=20).reserve() is True

    assert await FileRequestBudget(ledger, max_requests=1).reserve() is False
    assert await FileRequestBudget(ledger, max_requests=20).reserve() is False
    assert json.loads(ledger.read_text(encoding="utf-8"))["authorized_max_requests"] == 1


@pytest.mark.asyncio
async def test_corrupt_file_budget_fails_closed_without_replacing_evidence(tmp_path: Path) -> None:
    ledger = tmp_path / "budget.json"
    ledger.write_text("not-json", encoding="utf-8")
    budget = FileRequestBudget(ledger, max_requests=2)

    assert await budget.reserve() is False
    assert ledger.read_text(encoding="utf-8") == "not-json"


@pytest.mark.asyncio
async def test_symlink_budget_path_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "outside.json"
    ledger = tmp_path / "budget.json"
    ledger.symlink_to(target)

    assert await FileRequestBudget(ledger, max_requests=2).reserve() is False
    assert not target.exists()
    assert ledger.is_symlink()
