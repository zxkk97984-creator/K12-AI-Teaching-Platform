"""Explicit live acceptance against configured Bots, using only the isolated test DB."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.test_database import validate_test_database_url
from app.jobs import memory_worker, teaching_worker
from app.modules.ai.extraction import extract
from app.modules.ai.models import AIConfiguration
from app.modules.ai.schemas import RegistryData
from app.modules.memory.automatic import apply_extraction
from app.modules.memory.automatic_models import MemoryTask
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import create_app_client, csrf_headers, teaching_settings


@pytest.mark.skipif(
    os.environ.get("K12_KNODO_LIVE_ACCEPTANCE") != "1",
    reason="Requires explicit real Knodo acceptance and a server-owned registry snapshot",
)
@pytest.mark.asyncio
async def test_live_stage_routing_memory_correction_forget_and_owner_isolation(
    test_settings, content_session
):
    validate_test_database_url(test_settings.active_database_url)
    snapshot = json.loads(Path(os.environ["K12_AI_REGISTRY_SNAPSHOT"]).read_text())
    RegistryData.model_validate(snapshot["data"])
    content_session.add(AIConfiguration(id=1, revision=snapshot["revision"], data=snapshot["data"]))
    await content_session.commit()
    settings = teaching_settings(
        test_settings,
        gateway_mode="knodo",
        gateway_timeout_seconds=90,
        teaching_lease_seconds=600,
        memory_coalesce_seconds=0,
        memory_max_wait_seconds=1,
    )
    assert settings.active_database_url == test_settings.active_database_url
    owner = await create_synthetic_user(
        settings, username="live.acceptance.owner", password="synthetic-live-pass-1"
    )
    await create_synthetic_user(
        settings,
        username="live.acceptance.other",
        password="synthetic-live-pass-2",
        stage="JUNIOR",
        grade=8,
    )
    captured_requests = []
    extracted = []
    client = create_app_client(settings)
    gateway = client._transport.app.state.gateway
    invoke = gateway.invoke

    async def observe(operation, payload, **kwargs):
        captured_requests.append(deepcopy(payload))
        return await invoke(operation, payload, **kwargs)

    gateway.invoke = observe

    async def capture_extraction(runtime, payload, target):
        result = await extract(runtime, payload, target)
        extracted.append((payload, result))
        return result

    async def turn(expected_teacher, message):
        created = await client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(client)
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]
        assert created.json()["teacher"]["id"] == expected_teacher
        sent = await client.post(
            f"/api/v1/conversations/{session_id}/messages",
            json={"message": message, "idempotency_key": f"live-{session_id}"},
            headers=await csrf_headers(client),
        )
        assert sent.status_code == 202, sent.text
        print(f"LIVE request teacher={expected_teacher}", flush=True)
        status = await teaching_worker.execute_run(settings, gateway, sent.json()["run"]["id"])
        assert status == "SUCCEEDED", status
        detail = await client.get(f"/api/v1/conversations/{session_id}")
        assert detail.status_code == 200, detail.text
        assert len(detail.json()["messages"]) == 2
        print(f"LIVE saved reply teacher={expected_teacher}", flush=True)
        return session_id, detail.json()

    async def stage(value, grade):
        me = await client.get("/api/v1/me")
        changed = await client.patch(
            "/api/v1/me/profile",
            json={
                "base_revision": me.json()["profile"]["revision"],
                "stage": value,
                "grade": grade,
            },
            headers=await csrf_headers(client),
        )
        assert changed.status_code == 200, changed.text

    async def memory():
        response = await client.get("/api/v1/growth/personal-memory")
        assert response.status_code == 200, response.text
        return response.json()

    async def item_action(item, action, **fields):
        response = await client.post(
            f"/api/v1/growth/personal-memory/items/{item['id']}/events",
            json={"base_revision": item["revision"], "action": action, **fields},
            headers=await csrf_headers(client),
        )
        assert response.status_code == 200, response.text
        return response.json()

    try:
        async with client:
            assert (await login(client, owner.username, "synthetic-live-pass-1")).status_code == 200
            first_session, _ = await turn(
                "primary", "我喜欢观察星星，希望你用生活例子讲解。请简单解释人工智能。"
            )
            assert await memory_worker.run_once(settings, extractor=capture_extraction) == 1
            first_memory = await memory()
            assert first_memory["tasks"][0]["status"] == "SUCCEEDED", first_memory["tasks"]
            interest = next(
                item
                for item in first_memory["items"]
                if item["status"] == "ACTIVE" and "星" in item["statement"]
            )
            assert interest["sources"] and not interest["manual"]
            print("LIVE automatic extraction and local provenance saved", flush=True)

            for value, grade, teacher in [
                ("PRIMARY_UPPER", 5, "primary"),
                ("JUNIOR", 8, "junior"),
                ("SENIOR", 11, "senior"),
            ]:
                await stage(value, grade)
                await turn(teacher, "请结合我之前告诉你的兴趣，用一个例子解释人工智能。")
                items = captured_requests[-1]["personal_context"]["items"]
                assert any("星" in item["summary"] for item in items)
            print("LIVE all four stages and cross-teacher memory context passed", flush=True)

            edited = await item_action(
                interest, "EDIT", statement="现在更喜欢踢足球，希望使用足球例子理解知识。"
            )
            assert edited["manual"]
            await turn("senior", "请结合我目前喜欢的东西，解释人工智能。")
            items = captured_requests[-1]["personal_context"]["items"]
            assert any(
                item["source"] == "USER_EDITED" and "足球" in item["summary"] for item in items
            )
            assert not any("星" in item["summary"] for item in items)
            print("LIVE corrected memory reached a fresh remote conversation", flush=True)

            await item_action(edited, "FORGET")
            await turn("senior", "用一个生活例子解释监督学习。")
            request_text = json.dumps(captured_requests[-1], ensure_ascii=False)
            assert "观察星星" not in request_text and "踢足球" not in request_text
            payload, result = extracted[0]
            assert await apply_extraction(content_session, owner.id, result, payload.sources) == 0
            await content_session.commit()
            backfill = await client.post(
                "/api/v1/growth/personal-memory/backfill",
                json={"session_ids": [first_session]},
                headers=await csrf_headers(client),
            )
            assert backfill.status_code == 202, backfill.text
            tasks = list(
                await content_session.scalars(
                    select(MemoryTask).where(MemoryTask.session_id == first_session)
                )
            )
            assert len(tasks) == 1 and tasks[0].status == "SUCCEEDED"
            print(
                "LIVE forget excluded old context; replay/backfill did not resurrect it", flush=True
            )

            assert (
                await login(client, "live.acceptance.other", "synthetic-live-pass-2")
            ).status_code == 200
            await turn("junior", "请结合我的兴趣，简单解释人工智能。")
            assert captured_requests[-1].get("personal_context", {}).get("items", []) == []
            print("LIVE second student received no first-student personal memory", flush=True)
    finally:
        await gateway.aclose()
