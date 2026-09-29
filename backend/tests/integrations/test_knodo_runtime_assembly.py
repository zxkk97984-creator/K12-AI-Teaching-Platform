"""Knodo runtime assembly: live mode keeps its fixed targets and safety checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.integrations.knodo import build_gateway
from app.integrations.knodo.budget import UnlimitedRequestBudget


def base_settings(**overrides):
    payload = {
        "app_env": "test",
        "app_session_secret": "t" * 40,
        "test_database_url": "postgresql+asyncpg://u:p@127.0.0.1:55434/k12r1_test",
        "database_url": "postgresql+asyncpg://u:p@127.0.0.1:55433/k12r1_dev",
        "allowed_origins": "http://127.0.0.1:15173",
        "gateway_mode": "knodo",
        "knodo_base_url": "https://knodo.example.invalid",
        "knodo_tutor_bot_id": "tutor-bot-synthetic",
        "knodo_tutor_workspace_id": "tutor-workspace-synthetic",
        "knodo_designer_bot_id": "designer-bot-synthetic",
        "knodo_designer_workspace_id": "designer-workspace-synthetic",
        "knodo_max_requests": 20,
    }
    payload.update(overrides)
    return payload


def test_knodo_mode_requires_fixed_targets_and_nonnegative_optional_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNODO_PAT", "synthetic-pat-for-tests")

    for missing in (
        "knodo_tutor_bot_id",
        "knodo_tutor_workspace_id",
        "knodo_designer_bot_id",
        "knodo_designer_workspace_id",
    ):
        with pytest.raises(ValidationError):
            Settings(**base_settings(**{missing: None}))

    assert Settings(**base_settings(knodo_max_requests=0)).knodo_max_requests == 0
    assert Settings(**base_settings(knodo_max_requests=21)).knodo_max_requests == 21
    with pytest.raises(ValidationError):
        Settings(**base_settings(knodo_max_requests=-1))


@pytest.mark.parametrize(
    "base_url",
    [
        "http://knodo.example.invalid",
        "https://knodo.example.invalid/path",
        "https://user@knodo.example.invalid",
        "https://knodo.example.invalid?query=1",
    ],
)
def test_knodo_mode_requires_bare_https_origin(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
) -> None:
    monkeypatch.setenv("KNODO_PAT", "synthetic-pat-for-tests")
    with pytest.raises(ValidationError):
        Settings(**base_settings(knodo_base_url=base_url))


@pytest.mark.asyncio
async def test_build_gateway_enables_verified_mapper_without_exposing_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("KNODO_PAT", "synthetic-pat-for-tests")
    settings = Settings(
        **base_settings(knodo_budget_ledger_path=str(tmp_path / "private" / "budget.json"))
    )

    gateway = build_gateway(settings)
    public = gateway.status.to_public()

    assert public["available"] is True
    assert public["reason_code"] == "AVAILABLE"
    assert public["wire_mapper"] == "KNODO_BOT_CHAT_V1"
    rendered = json.dumps(public)
    assert "synthetic-pat-for-tests" not in rendered
    assert "tutor-bot-synthetic" not in rendered
    assert "tutor-workspace-synthetic" not in rendered
    await gateway.aclose()


@pytest.mark.asyncio
async def test_unlimited_gateway_ignores_exhausted_old_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("KNODO_PAT", "synthetic-pat-for-tests")
    ledger = tmp_path / "budget.json"
    previous_state = {
        "schema_version": "k12.knodo.request-budget.v1",
        "authorized_max_requests": 20,
        "reserved_requests": 20,
    }
    ledger.write_text(json.dumps(previous_state), encoding="utf-8")
    settings = Settings(**base_settings(knodo_max_requests=0, knodo_budget_ledger_path=str(ledger)))

    gateway = build_gateway(settings)
    try:
        assert isinstance(gateway._backend._budget, UnlimitedRequestBudget)
        for _ in range(21):
            assert await gateway._backend._budget.reserve() is True
        assert json.loads(ledger.read_text(encoding="utf-8")) == previous_state
    finally:
        await gateway.aclose()
