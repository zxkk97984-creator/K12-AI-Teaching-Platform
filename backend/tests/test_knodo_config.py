"""T10/QA38: fixture is dev/test only; missing knodo config never degrades silently."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.integrations.knodo import (
    GatewayConfigurationError,
    GatewayStatus,
    Operation,
    build_gateway,
)
from app.integrations.knodo import gateway as gateway_module
from app.integrations.knodo.schema_models import (
    CONTRACTS_DIR,
    MissingContractSchema,
    SchemaRegistry,
    default_registry,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def base_settings(**overrides) -> dict:
    payload = {
        "app_env": "test",
        "app_session_secret": "t" * 40,
        "test_database_url": "postgresql+asyncpg://u:p@127.0.0.1:55434/k12r1_test",
        "database_url": "postgresql+asyncpg://u:p@127.0.0.1:55433/k12r1_dev",
        "allowed_origins": "http://127.0.0.1:15173",
    }
    payload.update(overrides)
    return payload


def test_production_rejects_fixture_mode() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            **base_settings(
                app_env="production",
                cookie_secure=True,
                allowed_origins="https://k12.example.invalid",
                gateway_mode="fixture",
            )
        )
    assert "GATEWAY_MODE=fixture" in str(excinfo.value)


def test_knodo_mode_requires_base_url_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        Settings(**base_settings(gateway_mode="knodo"))

    monkeypatch.delenv("KNODO_PAT", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings(**base_settings(gateway_mode="knodo", knodo_base_url="https://knodo.invalid"))
    assert "KNODO_PAT" in str(excinfo.value)

    with pytest.raises(ValidationError):
        Settings(**base_settings(gateway_mode="knodo", knodo_base_url="not-a-url"))


def test_production_requires_https_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNODO_PAT", "synthetic-pat-for-tests")
    with pytest.raises(ValidationError):
        Settings(
            **base_settings(
                app_env="production",
                cookie_secure=True,
                allowed_origins="https://k12.example.invalid",
                gateway_mode="knodo",
                knodo_base_url="http://knodo.invalid",
            )
        )


@pytest.mark.asyncio
async def test_knodo_mode_stays_unavailable_until_the_wire_mapper_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNODO_PAT", "synthetic-pat-for-tests")
    settings = Settings(
        **base_settings(gateway_mode="knodo", knodo_base_url="https://knodo.invalid")
    )
    gateway = build_gateway(settings)
    status = gateway.status
    assert status.available is False
    assert status.reason_code == "WIRE_MAPPER_NOT_IMPLEMENTED_T11"
    assert status.wire_mapper == "NOT_IMPLEMENTED_T11"
    assert status.fixture is False

    payload = json.loads((EXAMPLES / "teaching-request.json").read_text(encoding="utf-8"))
    result = await gateway.invoke(Operation.TEACH_TURN.value, payload)
    assert result.status is GatewayStatus.FAILED
    assert result.error is not None and result.error.category.value == "CONFIG"
    # Never silently fall back to the fixture, and never invent upstream traffic.
    assert result.output is None
    assert result.fixture is False
    assert result.mode == "knodo"
    assert result.usage.upstream_calls == 0


@pytest.mark.asyncio
async def test_disabled_mode_never_masquerades_as_fixture() -> None:
    settings = Settings(**base_settings(gateway_mode="disabled"))
    gateway = build_gateway(settings)
    assert gateway.status.available is False
    payload = json.loads((EXAMPLES / "teaching-request.json").read_text(encoding="utf-8"))
    result = await gateway.invoke(Operation.TEACH_TURN.value, payload)
    assert result.status is GatewayStatus.FAILED
    assert result.error is not None and result.error.reason_code == "GATEWAY_DISABLED"
    assert result.fixture is False
    assert result.output is None


def test_missing_contract_files_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(MissingContractSchema):
        SchemaRegistry(tmp_path)
    with pytest.raises(MissingContractSchema):
        SchemaRegistry(CONTRACTS_DIR / "examples")


def test_build_gateway_wraps_missing_contracts_as_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom():
        raise MissingContractSchema("synthetic missing schema")

    monkeypatch.setattr(gateway_module, "default_registry", boom)
    settings = Settings(**base_settings(gateway_mode="fixture"))
    with pytest.raises(GatewayConfigurationError):
        build_gateway(settings)


def test_default_registry_reads_the_repository_contracts() -> None:
    registry = default_registry()
    assert registry.schema_dir == CONTRACTS_DIR
    assert registry.contract_version == "1.0.0"
    assert registry.wire_status == "LOCAL_SEMANTIC_ONLY_NOT_KNODO_HTTP"
