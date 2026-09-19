"""T12 acceptance E1–E4, E7, E8, E10: idempotency, leases, owner, recovery."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.jobs import teaching_worker
from app.modules.identity.dependencies import SessionContext  # noqa: F401  (import parity)
from app.modules.teaching.models import AgentRun, ConversationMessage, LessonSession, RunStatus
from app.modules.teaching.service import (
    acquire_lease,
    create_session,
    finalize_run,
    recover_expired_runs,
)
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    prepare_fixture_course,
    teaching_settings,
)


async def _student(settings: Settings, name: str, *, stage: str = "PRIMARY_LOWER", grade: int = 2):
    return await create_synthetic_user(
        settings, username=name, password="synthetic-pass-1", stage=stage, grade=grade
    )


async def _open_session(db, settings: Settings, user, chapter_id) -> LessonSession:
    return await create_session(db, settings=settings, user=user, chapter_id=chapter_id)


def _factory(settings: Settings):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import get_engine

    return async_sessionmaker(
        get_engine(settings.active_database_url, settings.app_env), expire_on_commit=False
    )


async def _count(db, model) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_turn_short_transaction_then_worker_single_side_effect(
    content_session, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.student.a")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        response = await login(client, "t12.student.a", "synthetic-pass-1")
        assert response.status_code == 200
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "我想了解规则", "idempotency_key": "key-1"},
            headers=await csrf_headers(client),
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["run"]["id"]
        assert created.json()["run"]["status"] in {"QUEUED", "RUNNING"}
        # The 202 response is produced before the gateway work is observable.

        original = teaching_worker.execute_run

        async def spy_execute(settings_arg, gateway, run_id_arg, *, cancel_signal=None):
            return await original(settings_arg, gateway, run_id_arg, cancel_signal=cancel_signal)

        monkeypatch.setattr(teaching_worker, "execute_run", spy_execute)
        status = await teaching_worker.execute_run(
            settings, client._transport.app.state.gateway, run_id
        )

    assert status == RunStatus.SUCCEEDED.value
    assert await _count(content_session, AgentRun) == 1
    assert await _count(content_session, ConversationMessage) == 2
    run = await content_session.scalar(select(AgentRun))
    assert run.owner_user_id == user.id
    assert run.gateway_invocation_id
    message = await content_session.scalar(
        select(ConversationMessage).where(ConversationMessage.role == "ASSISTANT")
    )
    assert message is not None and message.card is not None
    assert message.card["fixture"] is True
    assert "message_markdown" in message.card


@pytest.mark.asyncio
async def test_worker_never_holds_a_transaction_across_the_gateway_call(
    content_session, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.student.tx")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.student.tx", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "事务边界", "idempotency_key": "key-tx"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        gateway = client._transport.app.state.gateway

    # Prove the transaction boundary structurally: no worker DB session may be
    # open while the gateway is being called.
    observed: list[int] = []
    opened = {"count": 0}
    real_factory = teaching_worker.session_factory

    def counting_factory(settings_arg):
        real_sessions = real_factory(settings_arg)

        @asynccontextmanager
        async def factory():
            opened["count"] += 1
            try:
                async with real_sessions() as session:
                    yield session
            finally:
                opened["count"] -= 1

        return factory

    monkeypatch.setattr(teaching_worker, "session_factory", counting_factory)
    original = gateway._backend.invoke  # type: ignore[attr-defined]

    async def spy_invoke(operation, payload, **kwargs):
        observed.append(opened["count"])
        return await original(operation, payload, **kwargs)

    gateway._backend.invoke = spy_invoke  # type: ignore[attr-defined]
    status = await teaching_worker.execute_run(settings, gateway, str(run_id))
    assert status == RunStatus.SUCCEEDED.value
    assert observed == [0], f"gateway was called with open transactions: {observed}"


@pytest.mark.asyncio
async def test_idempotent_replay_and_conflict(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    await _student(settings, "t12.student.b")
    session = await _open_session(
        content_session, settings, await _student(settings, "t12.student.b"), revision.chapter_id
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.student.b", "synthetic-pass-1")
        first = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "同一个意图", "idempotency_key": "same-key"},
            headers=await csrf_headers(client),
        )
        second = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "同一个意图", "idempotency_key": "same-key"},
            headers=await csrf_headers(client),
        )
        conflict = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "不同的意图", "idempotency_key": "same-key"},
            headers=await csrf_headers(client),
        )

    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    assert second.json()["run"]["idempotent_replay"] is True
    assert conflict.status_code == 409
    assert await _count(content_session, AgentRun) == 1


@pytest.mark.asyncio
async def test_concurrent_same_intent_creates_one_run(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.student.c")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.student.c", "synthetic-pass-1")
        body = {"message": "并发双击", "idempotency_key": "double-click"}
        headers = await csrf_headers(client)  # fetch once: the token rotates
        first, second = await asyncio.gather(
            client.post(f"/api/v1/lesson-sessions/{session.id}/turns", json=body, headers=headers),
            client.post(f"/api/v1/lesson-sessions/{session.id}/turns", json=body, headers=headers),
        )

    assert first.status_code == second.status_code == 202
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    assert await _count(content_session, AgentRun) == 1
    assert await _count(content_session, ConversationMessage) == 1  # one user message only


@pytest.mark.asyncio
async def test_owner_isolation_for_read_subscribe_and_cancel(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    owner = await _student(settings, "t12.owner")
    other = await _student(settings, "t12.other")
    session = await _open_session(content_session, settings, owner, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.owner", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "只有我能看", "idempotency_key": "owner-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        await client.post("/api/v1/auth/logout", headers=await csrf_headers(client))

        await login(client, "t12.other", "synthetic-pass-1")
        assert (await client.get(f"/api/v1/lesson-sessions/{session.id}")).status_code == 404
        assert (await client.get(f"/api/v1/agent-runs/{run_id}")).status_code == 404
        assert (await client.get(f"/api/v1/agent-runs/{run_id}/events")).status_code == 404
        assert (
            await client.post(
                f"/api/v1/agent-runs/{run_id}/cancel", headers=await csrf_headers(client)
            )
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/lesson-sessions/{session.id}/turns",
                json={"message": "越权", "idempotency_key": "intruder"},
                headers=await csrf_headers(client),
            )
        ).status_code == 404
    assert other.id is not None


@pytest.mark.asyncio
async def test_expired_lease_marks_stale_and_late_worker_cannot_overwrite(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.stale")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.stale", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "迟到", "idempotency_key": "stale-key"},
            headers=await csrf_headers(client),
        )
        run_id = uuid.UUID(created.json()["run"]["id"])

    # Each phase uses its own session, exactly like the worker does.
    factory = _factory(settings)
    async with factory() as db:
        token = await acquire_lease(db, run_id=run_id, ttl_seconds=10)
    assert token is not None
    async with factory() as db:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
        run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)
        await db.commit()

    async with factory() as db:
        status = await finalize_run(
            db,
            run_id=run_id,
            lease_token=token,
            assistant={"message_markdown": "迟到结果"},
        )
    assert status == RunStatus.STALE.value

    async with factory() as db:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
        assert run.stale_reason == "LEASE_EXPIRED"
        assert await _count(db, ConversationMessage) == 1  # only the user message

    async with factory() as db:
        status = await finalize_run(db, run_id=run_id, lease_token=token, error_category="UNKNOWN")
        assert status == RunStatus.STALE.value


@pytest.mark.asyncio
async def test_recovery_after_restart_marks_stale_without_reinvoking(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.recover")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.recover", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "重启恢复", "idempotency_key": "recover-key"},
            headers=await csrf_headers(client),
        )
        run_id = uuid.UUID(created.json()["run"]["id"])

    factory = _factory(settings)
    async with factory() as db:
        token = await acquire_lease(db, run_id=run_id, ttl_seconds=10)
    assert token is not None
    async with factory() as db:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
        run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async with factory() as db:
        recovered = await recover_expired_runs(db)
        assert recovered == 1
    async with factory() as db:
        run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
        assert run.status == RunStatus.STALE.value
        assert run.stale_reason == "RECOVERED_AFTER_RESTART"
        assert await _count(db, ConversationMessage) == 1


@pytest.mark.asyncio
async def test_lease_is_the_mutual_exclusion_not_a_process_flag(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.lease")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.lease", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "并发worker", "idempotency_key": "lease-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        gateway = client._transport.app.state.gateway

    calls = 0
    original = gateway._backend.invoke  # type: ignore[attr-defined]

    async def counting_invoke(operation, payload, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return await original(operation, payload, **kwargs)

    gateway._backend.invoke = counting_invoke  # type: ignore[attr-defined]
    outcomes = await asyncio.gather(
        teaching_worker.execute_run(settings, gateway, str(run_id)),
        teaching_worker.execute_run(settings, gateway, str(run_id)),
    )
    assert calls == 1, outcomes
    assert RunStatus.SUCCEEDED.value in outcomes
    assert "LEASE_HELD" in outcomes


@pytest.mark.asyncio
async def test_cancel_queued_run_prevents_execution(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.cancel")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.cancel", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "先取消", "idempotency_key": "cancel-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        cancelled = await client.post(
            f"/api/v1/agent-runs/{run_id}/cancel", headers=await csrf_headers(client)
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == RunStatus.CANCELLED.value
        outcome = await teaching_worker.execute_run(
            settings, client._transport.app.state.gateway, run_id
        )

    assert outcome == "LEASE_HELD"
    assert await _count(content_session, ConversationMessage) == 1
    run = await content_session.scalar(select(AgentRun))
    assert run.status == RunStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_upstream_failure_is_persisted_without_assistant_message(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.upstream")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.upstream", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "上游故障", "idempotency_key": "upstream-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        gateway = client._transport.app.state.gateway

        from app.integrations.knodo.fixture import FixtureScenario

        original_backend_invoke = gateway._backend.invoke  # type: ignore[attr-defined]

        async def failing_invoke(operation, payload, **kwargs):
            kwargs["scenario"] = FixtureScenario.SERVER_500
            return await original_backend_invoke(operation, payload, **kwargs)

        gateway._backend.invoke = failing_invoke  # type: ignore[attr-defined]
        outcome = await teaching_worker.execute_run(settings, gateway, run_id)

    assert outcome == RunStatus.FAILED.value
    run = await content_session.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    assert run.error_category == "SERVER"
    assert await _count(content_session, ConversationMessage) == 1


@pytest.mark.asyncio
async def test_save_failure_leaves_no_fake_success(
    content_session, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t12.save")
    session = await _open_session(content_session, settings, user, revision.chapter_id)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.save", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "保存失败", "idempotency_key": "save-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        gateway = client._transport.app.state.gateway

    original_finalize = teaching_worker.finalize_run
    calls = {"count": 0}

    async def flaky_finalize(db, **kwargs):
        if kwargs.get("assistant") is not None and calls["count"] == 0:
            calls["count"] += 1
            raise RuntimeError("synthetic save failure")
        return await original_finalize(db, **kwargs)

    monkeypatch.setattr(teaching_worker, "finalize_run", flaky_finalize)
    outcome = await teaching_worker.execute_run(settings, gateway, run_id)
    assert outcome == RunStatus.FAILED.value
    run = await content_session.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    await content_session.refresh(run)
    assert run.status == RunStatus.FAILED.value
    assert run.error_category == "SAVE_FAILED"
    assert await _count(content_session, ConversationMessage) == 1
