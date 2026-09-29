"""Acceptance coverage for the free conversation surface."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.jobs import teaching_worker
from app.modules.teaching.models import LessonSession
from app.modules.teaching.service import acquire_lease, finalize_run
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import create_app_client, csrf_headers, teaching_settings


@pytest.mark.asyncio
async def test_free_conversation_crud_and_knodo_turn(content_session, test_settings):
    settings = teaching_settings(test_settings)
    await create_synthetic_user(
        settings,
        username="free.conv.student",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=7,
    )
    client = create_app_client(settings)
    async with client:
        assert (await login(client, "free.conv.student", "synthetic-pass-1")).status_code == 200
        created = await client.post(
            "/api/v1/conversations",
            json={},
            headers=await csrf_headers(client),
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["conversation_type"] == "FREE"
        assert payload["chapter_id"] is None
        session_id = payload["id"]

        sent = await client.post(
            f"/api/v1/conversations/{session_id}/messages",
            json={"message": "解释一下 Python 条件判断", "idempotency_key": "free-turn-1"},
            headers=await csrf_headers(client),
        )
        assert sent.status_code == 202, sent.text
        run_id = sent.json()["run"]["id"]
        status = await teaching_worker.execute_run(
            settings, client._transport.app.state.gateway, run_id
        )
        assert status == "SUCCEEDED"

        detail = await client.get(f"/api/v1/conversations/{session_id}")
        assert detail.status_code == 200, detail.text
        assert len(detail.json()["messages"]) == 2
        assert detail.json()["title"] == "解释一下 Python 条件判断"

        renamed = await client.patch(
            f"/api/v1/conversations/{session_id}",
            json={"title": "Python 入门"},
            headers=await csrf_headers(client),
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Python 入门"

        archived = await client.patch(
            f"/api/v1/conversations/{session_id}",
            json={"archived": True},
            headers=await csrf_headers(client),
        )
        assert archived.status_code == 200
        assert (await client.get("/api/v1/conversations")).json() == []
        listed = await client.get("/api/v1/conversations?include_archived=true")
        assert listed.status_code == 200
        assert listed.json()[0]["archived_at"] is not None

        deleted = await client.delete(
            f"/api/v1/conversations/{session_id}",
            headers=await csrf_headers(client),
        )
        assert deleted.status_code == 204

    deleted_row = await content_session.scalar(
        select(LessonSession).where(LessonSession.id == session_id)
    )
    assert deleted_row is None


@pytest.mark.asyncio
async def test_only_free_conversation_page_publishes_provisional_text(
    content_session, test_settings
):
    settings = teaching_settings(test_settings)
    await create_synthetic_user(
        settings,
        username="free.conv.draft",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=7,
    )
    client = create_app_client(settings)
    async with client:
        await login(client, "free.conv.draft", "synthetic-pass-1")
        created = await client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(client)
        )
        assert created.status_code == 201
        session_id = created.json()["id"]
        gateway = client._transport.app.state.gateway
        real_invoke = gateway.invoke
        visible_during_run: list[str | None] = []
        active_run_id = ""

        async def observe_invoke(operation, payload, **kwargs):
            await kwargs["on_content"]("这是一段正在生成的自由对话解释，供学生逐步阅读。" * 2)
            snapshot = await client.get(f"/api/v1/agent-runs/{active_run_id}")
            assert snapshot.status_code == 200
            visible_during_run.append(snapshot.json()["draft_markdown"])
            return await real_invoke(operation, payload, **kwargs)

        gateway.invoke = observe_invoke
        for index, scene in enumerate(
            (
                {"page_type": "conversation", "route": "/conversations?session=" + session_id},
                {"page_type": "practice", "route": "/practice"},
            )
        ):
            sent = await client.post(
                f"/api/v1/conversations/{session_id}/messages",
                json={
                    "message": f"第{index + 1}轮提问",
                    "idempotency_key": f"free-draft-{index}",
                    "scene": scene,
                },
                headers=await csrf_headers(client),
            )
            assert sent.status_code == 202
            active_run_id = sent.json()["run"]["id"]
            assert (
                await teaching_worker.execute_run(settings, gateway, active_run_id) == "SUCCEEDED"
            )

        assert visible_during_run[0]
        assert visible_during_run[1] is None
        final = await client.get(f"/api/v1/agent-runs/{active_run_id}")
        assert final.json()["draft_markdown"] is None


@pytest.mark.asyncio
async def test_conversation_detail_reports_only_owners_active_run(content_session, test_settings):
    settings = teaching_settings(test_settings, teaching_autorun=False)
    for username in ("free.conv.active.owner", "free.conv.active.other"):
        await create_synthetic_user(
            settings,
            username=username,
            password="synthetic-pass-1",
            stage="JUNIOR",
            grade=7,
        )
    owner_client = create_app_client(settings)
    other_client = create_app_client(settings)
    async with owner_client, other_client:
        await login(owner_client, "free.conv.active.owner", "synthetic-pass-1")
        await login(other_client, "free.conv.active.other", "synthetic-pass-1")
        opened = await owner_client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(owner_client)
        )
        assert opened.status_code == 201
        session_id = opened.json()["id"]
        sent = await owner_client.post(
            f"/api/v1/conversations/{session_id}/messages",
            json={"message": "未完成的提问", "idempotency_key": "active-detail-1"},
            headers=await csrf_headers(owner_client),
        )
        assert sent.status_code == 202
        run_id = sent.json()["run"]["id"]

        queued = await owner_client.get(f"/api/v1/conversations/{session_id}")
        assert queued.status_code == 200
        assert queued.json()["active_run_id"] == run_id
        assert (await other_client.get(f"/api/v1/conversations/{session_id}")).status_code == 404

        token = await acquire_lease(content_session, run_id=uuid.UUID(run_id), ttl_seconds=60)
        assert token is not None
        running = await owner_client.get(f"/api/v1/conversations/{session_id}")
        assert running.json()["active_run_id"] == run_id

        assert (
            await finalize_run(
                content_session,
                run_id=uuid.UUID(run_id),
                lease_token=token,
                error_category="TEST_FAILURE",
            )
            == "FAILED"
        )
        terminal = await owner_client.get(f"/api/v1/conversations/{session_id}")
        assert terminal.json()["active_run_id"] is None


@pytest.mark.asyncio
async def test_saved_teacher_style_reaches_tutor_request(test_settings):
    settings = teaching_settings(test_settings)
    await create_synthetic_user(
        settings,
        username="free.conv.style",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=7,
    )
    client = create_app_client(settings)
    async with client:
        await login(client, "free.conv.style", "synthetic-pass-1")
        profile = (await client.get("/api/v1/me")).json()["profile"]
        saved = await client.patch(
            "/api/v1/me/preferences",
            json={"base_revision": profile["revision"], "teacher_style": "SOCRATIC"},
            headers=await csrf_headers(client),
        )
        assert saved.status_code == 200, saved.text
        opened = await client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(client)
        )
        session_id = opened.json()["id"]
        sent = await client.post(
            f"/api/v1/conversations/{session_id}/messages",
            json={"message": "请解释食物链", "idempotency_key": "style-turn-1"},
            headers=await csrf_headers(client),
        )
        assert sent.status_code == 202, sent.text
        gateway = client._transport.app.state.gateway
        original = gateway._backend.invoke
        requests = []

        async def inspect(operation, payload, **kwargs):
            requests.append(json.dumps(payload, ensure_ascii=False, default=str))
            return await original(operation, payload, **kwargs)

        gateway._backend.invoke = inspect
        assert (
            await teaching_worker.execute_run(settings, gateway, sent.json()["run"]["id"])
            == "SUCCEEDED"
        )
        assert any("教师表达方式：启发提问" in payload for payload in requests)


@pytest.mark.asyncio
async def test_primary_memory_reaches_only_its_owners_tutor_request(test_settings):
    settings = teaching_settings(test_settings)
    owner = await create_synthetic_user(
        settings,
        username="free.conv.memory-owner",
        password="synthetic-pass-1",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    await create_synthetic_user(
        settings,
        username="free.conv.memory-other",
        password="synthetic-pass-2",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    async with create_app_client(settings) as client:
        assert (await login(client, owner.username, "synthetic-pass-1")).status_code == 200
        document = await client.post(
            "/api/v1/growth/documents",
            json={
                "title": "个人记忆.md",
                "category": "NOTE",
                "is_primary": True,
                "content_markdown": "我喜欢画圆形来理解分数。",
            },
            headers=await csrf_headers(client),
        )
        assert document.status_code == 200, document.text
        assert document.json()["ai_enabled"] is True
        conversation = await client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(client)
        )
        sent = await client.post(
            f"/api/v1/conversations/{conversation.json()['id']}/messages",
            json={"message": "请解释二分之一", "idempotency_key": "primary-memory-owner-turn"},
            headers=await csrf_headers(client),
        )
        assert sent.status_code == 202, sent.text
        gateway = client._transport.app.state.gateway
        original = gateway._backend.invoke
        requests: list[dict] = []

        async def inspect(operation, payload, **kwargs):
            requests.append(payload)
            return await original(operation, payload, **kwargs)

        gateway._backend.invoke = inspect
        assert (
            await teaching_worker.execute_run(settings, gateway, sent.json()["run"]["id"])
            == "SUCCEEDED"
        )
        owner_evidence = requests[-1]["evidence"]
        assert any("我喜欢画圆形来理解分数" in item["summary"] for item in owner_evidence)
        assert any(
            item["id"].startswith(f"memory-document:{document.json()['id']}:v1")
            for item in owner_evidence
        )

        assert (
            await login(client, "free.conv.memory-other", "synthetic-pass-2")
        ).status_code == 200
        other_conversation = await client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(client)
        )
        other_sent = await client.post(
            f"/api/v1/conversations/{other_conversation.json()['id']}/messages",
            json={"message": "请解释二分之一", "idempotency_key": "primary-memory-other-turn"},
            headers=await csrf_headers(client),
        )
        assert other_sent.status_code == 202, other_sent.text
        assert (
            await teaching_worker.execute_run(settings, gateway, other_sent.json()["run"]["id"])
            == "SUCCEEDED"
        )
        assert all(
            "我喜欢画圆形来理解分数" not in item["summary"] for item in requests[-1]["evidence"]
        )
