"""T10/D7: every invocation owns its usage and output; no shared last_usage."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.integrations.knodo import GatewayStatus, Operation, build_gateway
from app.integrations.knodo.fixture import FixtureScenario

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def settings() -> Settings:
    return Settings(
        app_env="test",
        app_session_secret="t" * 40,
        test_database_url="postgresql+asyncpg://u:p@127.0.0.1:55434/k12r1_test",
        database_url="postgresql+asyncpg://u:p@127.0.0.1:55433/k12r1_dev",
        allowed_origins="http://127.0.0.1:15173",
        gateway_mode="fixture",
        gateway_timeout_seconds=5,
    )


def load(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def tagged(name: str, request_id: str) -> dict:
    payload = load(name)
    payload["request_id"] = request_id
    return payload


@pytest.mark.asyncio
async def test_parallel_invocations_never_share_usage_or_output() -> None:
    gateway = build_gateway(settings())
    plan = (
        [
            (
                Operation.TEACH_TURN,
                tagged("teaching-request", f"synthetic-{index}"),
                FixtureScenario.SUCCESS,
            )
            for index in range(4)
        ]
        + [
            (
                Operation.QUIZ_DRAFT,
                tagged("designer-request", f"synthetic-quiz-{index}"),
                FixtureScenario.SUCCESS,
            )
            for index in range(3)
        ]
        + [
            (
                Operation.TEACH_TURN,
                tagged("teaching-request", "synthetic-fail"),
                FixtureScenario.SERVER_500,
            ),
            (
                Operation.QUIZ_DRAFT,
                tagged("designer-request", "synthetic-rate"),
                FixtureScenario.RATE_429,
            ),
        ]
    )

    results = await asyncio.gather(
        *[
            gateway.invoke(operation.value, payload, scenario=scenario)
            for operation, payload, scenario in plan
        ]
    )

    assert len({result.invocation_id for result in results}) == len(plan)
    for (operation, payload, scenario), result in zip(plan, results, strict=True):
        assert result.operation is operation
        if scenario is FixtureScenario.SUCCESS:
            assert result.status is GatewayStatus.OK
            assert result.output is not None
            assert result.output["request_id"] == payload["request_id"]
            assert result.usage.output_bytes == len(
                json.dumps(result.output, ensure_ascii=False).encode("utf-8")
            )
        else:
            assert result.status is GatewayStatus.FAILED
            assert result.output is None
            assert result.usage.output_bytes == 0
        assert result.usage.input_bytes > 0

    # The gateway keeps no mutable per-request state at all.
    assert not hasattr(gateway, "last_usage")
    assert not hasattr(gateway, "last_result")


@pytest.mark.asyncio
async def test_concurrent_delays_do_not_mix_usage() -> None:
    gateway = build_gateway(settings())
    request = tagged("teaching-request", "synthetic-delay")

    fast, slow = await asyncio.gather(
        gateway.invoke(
            Operation.TEACH_TURN.value, request, scenario=FixtureScenario.DELAY, delay_seconds=0.05
        ),
        gateway.invoke(
            Operation.TEACH_TURN.value, request, scenario=FixtureScenario.DELAY, delay_seconds=0.35
        ),
    )
    assert fast.status is GatewayStatus.OK and slow.status is GatewayStatus.OK
    assert fast.invocation_id != slow.invocation_id
    assert fast.usage.duration_ms < slow.usage.duration_ms
    assert slow.usage.duration_ms >= 300


@pytest.mark.asyncio
async def test_failure_does_not_disturb_a_parallel_success() -> None:
    gateway = build_gateway(settings())
    ok_request = tagged("teaching-request", "synthetic-ok")
    bad_request = tagged("teaching-request", "synthetic-bad")

    ok, failed = await asyncio.gather(
        gateway.invoke(Operation.TEACH_TURN.value, ok_request),
        gateway.invoke(Operation.TEACH_TURN.value, bad_request, scenario=FixtureScenario.AUTH_401),
    )
    assert ok.status is GatewayStatus.OK
    assert ok.output is not None and ok.output["request_id"] == "synthetic-ok"
    assert failed.status is GatewayStatus.FAILED
    assert failed.output is None
