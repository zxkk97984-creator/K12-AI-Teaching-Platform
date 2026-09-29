"""T12 acceptance E5, E6, E8(cancel), E9: delivery, QA12/QA13, history."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.core import database as database_module
from app.integrations.knodo.errors import GatewayError, GatewayErrorCategory
from app.integrations.knodo.types import GatewayErrorInfo, GatewayStatus
from app.jobs import teaching_worker
from app.modules.teaching import router as teaching_router
from app.modules.teaching.models import AgentRun, ConversationMessage, RunStatus
from app.modules.teaching.service import (
    acquire_lease,
    create_session,
    finalize_run,
    update_run_draft,
)
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    prepare_fixture_course,
    teaching_settings,
)


async def _setup(settings: Settings, db, name: str = "t12.delivery"):
    revision = await prepare_fixture_course(db)
    user = await create_synthetic_user(
        settings, username=name, password="synthetic-pass-1", stage="PRIMARY_LOWER", grade=2
    )
    session = await create_session(db, settings=settings, user=user, chapter_id=revision.chapter_id)
    return user, session


async def _count(db, model) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def _read_sse_until(client, run_id: str, terminal_event: str, *, timeout: float = 10.0):
    events: list[tuple[str, dict]] = []
    async with asyncio.timeout(timeout):
        async with client.stream("GET", f"/api/v1/agent-runs/{run_id}/events") as response:
            assert response.status_code == 200, response.status_code
            event = "message"
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ").strip()
                elif line.startswith("data: "):
                    payload = json.loads(line.removeprefix("data: "))
                    events.append((event, payload))
                    if event == terminal_event:
                        return events
    raise AssertionError(f"terminal event {terminal_event} not observed: {events}")


@pytest.mark.asyncio
async def test_sse_delivers_progress_and_done_without_restarting(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings, teaching_autorun=True)
    user, session = await _setup(settings, content_session)

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.delivery", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "讲一讲规则", "idempotency_key": "sse-key"},
            headers=await csrf_headers(client),
        )
        assert created.status_code == 202
        run_id = created.json()["run"]["id"]

        events = await _read_sse_until(client, run_id, "done")
        done = [payload for event, payload in events if event == "done"][0]
        assert done["status"] == RunStatus.SUCCEEDED.value
        assert done["card"]["fixture"] is True
        assert done["card"]["message_markdown"]
        assert done["result_message_id"]

        # Reconnect reads the stored run: no new gateway call, same card.
        again = await _read_sse_until(client, run_id, "done")
        assert [payload for event, payload in again if event == "done"][0]["card"] == done["card"]

        gateway_calls = await _count(content_session, AgentRun)
        assert gateway_calls == 1
        assert await _count(content_session, ConversationMessage) == 2


@pytest.mark.asyncio
async def test_reconnect_via_rest_endpoint_does_not_reinvoke_gateway(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    user, session = await _setup(settings, content_session, "t12.reconnect")

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.reconnect", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "刷新页面", "idempotency_key": "reload-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        await teaching_worker.execute_run(settings, client._transport.app.state.gateway, run_id)
        first = await client.get(f"/api/v1/agent-runs/{run_id}")
        second = await client.get(f"/api/v1/agent-runs/{run_id}")
        history = await client.get(f"/api/v1/lesson-sessions/{session.id}")

    assert first.json() == second.json()
    assert first.json()["status"] == RunStatus.SUCCEEDED.value
    body = history.json()
    roles = [message["role"] for message in body["messages"]]
    assert roles == ["USER", "ASSISTANT"]
    assert body["messages"][1]["card"]["fixture"] is True


@pytest.mark.asyncio
async def test_draft_survives_reconnect_and_disappears_on_cancel(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings, teaching_autorun=False)
    _, session = await _setup(settings, content_session, "t12.streamdraft")
    client = create_app_client(settings)
    async with client:
        await login(client, "t12.streamdraft", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "解释一下", "idempotency_key": "draft-key"},
            headers=await csrf_headers(client),
        )
        assert created.status_code == 202
        run_id = uuid.UUID(created.json()["run"]["id"])
        token = await acquire_lease(content_session, run_id=run_id, ttl_seconds=60)
        assert token is not None
        assert await update_run_draft(
            content_session,
            run_id=run_id,
            lease_token=token,
            markdown="这是暂存的解释",
        )

        first = await client.get(f"/api/v1/agent-runs/{run_id}")
        second = await client.get(f"/api/v1/agent-runs/{run_id}")
        assert first.json()["draft_markdown"] == second.json()["draft_markdown"]
        assert first.json()["draft_markdown"] == "这是暂存的解释"
        history = await client.get(f"/api/v1/lesson-sessions/{session.id}")
        assert [item["role"] for item in history.json()["messages"]] == ["USER"]

        cancelled = await client.post(
            f"/api/v1/agent-runs/{run_id}/cancel", headers=await csrf_headers(client)
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["draft_markdown"] is None
        assert not await update_run_draft(
            content_session,
            run_id=run_id,
            lease_token=token,
            markdown="迟到的文本",
        )
        status = await finalize_run(content_session, run_id=run_id, lease_token=token)
        assert status == RunStatus.CANCELLED.value
        terminal = await client.get(f"/api/v1/agent-runs/{run_id}")
        assert terminal.json()["draft_markdown"] is None


@pytest.mark.asyncio
async def test_two_active_sse_connections_leave_pool_available_for_reads(
    content_session, test_settings: Settings, monkeypatch
):
    """Regression for 2-slot pool exhaustion by long-lived FastAPI dependencies."""

    settings = teaching_settings(test_settings, teaching_autorun=False)
    _, session = await _setup(settings, content_session, "t12.ssepool")
    engine = create_async_engine(
        settings.active_database_url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.5,
        connect_args={"timeout": 2},
    )
    monkeypatch.setattr(database_module, "get_engine", lambda *_: engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    stream_tasks: set[asyncio.Task] = set()
    both_started = asyncio.Event()

    def tracking_factory(_settings):
        def open_session():
            @asynccontextmanager
            async def managed():
                task = asyncio.current_task()
                if task is not None:
                    stream_tasks.add(task)
                    if len(stream_tasks) >= 2:
                        both_started.set()
                async with factory() as db:
                    yield db

            return managed()

        return open_session

    monkeypatch.setattr(teaching_router, "session_factory", tracking_factory)
    client = create_app_client(settings)
    pending: list[asyncio.Task] = []
    try:
        async with client:
            await login(client, "t12.ssepool", "synthetic-pass-1")
            created = await client.post(
                f"/api/v1/lesson-sessions/{session.id}/turns",
                json={"message": "等待回答", "idempotency_key": "pool-key"},
                headers=await csrf_headers(client),
            )
            assert created.status_code == 202
            run_id = created.json()["run"]["id"]
            url = f"/api/v1/agent-runs/{run_id}/events"
            pending = [asyncio.create_task(client.get(url)) for _ in range(2)]
            await asyncio.wait_for(both_started.wait(), timeout=3)
            run_response = await asyncio.wait_for(
                client.get(f"/api/v1/agent-runs/{run_id}"), timeout=3
            )
            history_response = await asyncio.wait_for(
                client.get(f"/api/v1/lesson-sessions/{session.id}"), timeout=3
            )
            assert run_response.status_code == 200
            assert history_response.status_code == 200
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()


@pytest.mark.asyncio
async def test_bad_model_payload_is_rejected_without_raw_json_or_writes(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    user, session = await _setup(settings, content_session, "t12.badjson")

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.badjson", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "坏输出", "idempotency_key": "bad-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        gateway = client._transport.app.state.gateway
        real_invoke = gateway.invoke

        async def broken_invoke(operation, payload, **kwargs):
            result = await real_invoke(operation, payload, **kwargs)
            polluted = dict(result.output or {})
            polluted["totally_unknown"] = "RAW-PAYLOAD-SENTINEL"
            return result.model_copy(update={"output": polluted})

        gateway.invoke = broken_invoke
        outcome = await teaching_worker.execute_run(settings, gateway, run_id)

    assert outcome == RunStatus.FAILED.value
    run = await content_session.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    assert run.error_category == "RESPONSE_SCHEMA_MISMATCH"
    assert await _count(content_session, ConversationMessage) == 1  # user message only
    stored = await content_session.scalar(
        select(ConversationMessage.content_markdown).where(ConversationMessage.role == "ASSISTANT")
    )
    assert stored is None
    assert "RAW-PAYLOAD-SENTINEL" not in json.dumps(run.__dict__, default=str)


@pytest.mark.asyncio
async def test_fake_source_and_resource_are_rejected_qa13(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    user, session = await _setup(settings, content_session, "t12.fake")

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.fake", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "假来源", "idempotency_key": "fake-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        gateway = client._transport.app.state.gateway
        real_invoke = gateway.invoke
        running_draft = "not-checked"

        async def faking_invoke(operation, payload, **kwargs):
            nonlocal running_draft
            result = await real_invoke(operation, payload, **kwargs)
            await kwargs["on_content"]("这段课程解释未经来源审查，不得提前显示给学生。")
            during_run = await client.get(f"/api/v1/agent-runs/{run_id}")
            assert during_run.status_code == 200
            running_draft = during_run.json()["draft_markdown"]
            forged = dict(result.output or {})
            forged["source_refs"] = [
                {"source_id": "totally-made-up-source", "revision": "v9", "locator": "nope"}
            ]
            return result.model_copy(update={"output": forged})

        gateway.invoke = faking_invoke
        outcome = await teaching_worker.execute_run(settings, gateway, run_id)

    assert outcome == RunStatus.FAILED.value
    run = await content_session.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    assert run.error_category == "SOURCE_NOT_ALLOWED"
    assert running_draft is None
    assert run.draft_markdown is None
    assert await _count(content_session, ConversationMessage) == 1


@pytest.mark.asyncio
async def test_upstream_unknown_is_persisted_honestly(
    content_session, test_settings: Settings, caplog
):
    settings = teaching_settings(test_settings)
    user, session = await _setup(settings, content_session, "t12.unknown")

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.unknown", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "未知上游", "idempotency_key": "unknown-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        gateway = client._transport.app.state.gateway
        real_invoke = gateway.invoke

        async def unknown_invoke(operation, payload, **kwargs):
            result = await real_invoke(operation, payload, **kwargs)
            return result.model_copy(
                update={
                    "status": GatewayStatus.FAILED,
                    "output": None,
                    "error": GatewayErrorInfo.from_error(
                        GatewayError(GatewayErrorCategory.UNKNOWN, "UPSTREAM_CONNECTION_ERROR")
                    ),
                }
            )

        gateway.invoke = unknown_invoke
        outcome = await teaching_worker.execute_run(settings, gateway, run_id)

    assert outcome == RunStatus.FAILED.value
    run = await content_session.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    assert run.error_category == "UNKNOWN"
    assert await _count(content_session, ConversationMessage) == 1
    assert '"reason_code":"UPSTREAM_CONNECTION_ERROR"' in caplog.text
    assert '"upstream_calls":' in caplog.text
    assert "未知上游" not in caplog.text


@pytest.mark.asyncio
async def test_cancel_during_run_discards_a_late_success(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    user, session = await _setup(settings, content_session, "t12.cancelmid")

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.cancelmid", "synthetic-pass-1")
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "中途取消", "idempotency_key": "mid-key"},
            headers=await csrf_headers(client),
        )
        run_id = uuid.UUID(created.json()["run"]["id"])
        run = await content_session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        run.cancel_requested_at = datetime.now(UTC)
        await content_session.commit()

    token = await acquire_lease(content_session, run_id=run_id, ttl_seconds=30)
    assert token is not None
    status = await finalize_run(
        content_session,
        run_id=run_id,
        lease_token=token,
        assistant={"message_markdown": "迟到的成功"},
    )
    assert status == RunStatus.CANCELLED.value
    assert await _count(content_session, ConversationMessage) == 1


@pytest.mark.asyncio
async def test_history_endpoint_shows_real_records(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    user, session = await _setup(settings, content_session, "t12.history")

    client = create_app_client(settings)
    async with client:
        await login(client, "t12.history", "synthetic-pass-1")
        before = await client.get("/api/v1/lesson-sessions")
        assert before.status_code == 200
        assert [item["message_count"] for item in before.json()] == [0]

        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "历史记录", "idempotency_key": "history-key"},
            headers=await csrf_headers(client),
        )
        run_id = created.json()["run"]["id"]
        await teaching_worker.execute_run(settings, client._transport.app.state.gateway, run_id)
        listing = await client.get("/api/v1/lesson-sessions")
        detail = await client.get(f"/api/v1/lesson-sessions/{session.id}")

    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["message_count"] == 2
    assert items[0]["chapter_title"]
    body = detail.json()
    assert body["messages"][0]["content_markdown"] == "历史记录"
    assert body["messages"][1]["card"]["message_markdown"]
    assert [message["run_id"] for message in body["messages"]] == [run_id, run_id]
