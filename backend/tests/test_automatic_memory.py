import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.jobs.memory_worker import run_once
from app.modules.ai.models import AIConfiguration
from app.modules.ai.schemas import RegistryData
from app.modules.ai.service import initial_data, resolve
from app.modules.memory.automatic import (
    KeywordMemoryRetriever,
    apply_extraction,
    delete_chat_memory,
    enqueue_run,
    history_backfill,
    item_action,
    settings_update,
    state_for,
)
from app.modules.memory.automatic_models import MemoryTask, PersonalMemoryItem
from app.modules.memory.contracts import ExtractionResponse, SourceMessage
from app.modules.memory.service import get_memory_context_revision
from app.modules.teaching.service import create_free_session, create_turn
from tests.identity_helpers import create_synthetic_user


async def student(settings, name="auto.memory"):
    return await create_synthetic_user(settings, username=name, password="synthetic-pass-1")


def source(text="我喜欢天文。", session_id=None):
    return SourceMessage(
        id=str(uuid.uuid4()),
        session_id=str(session_id or uuid.uuid4()),
        text=text,
        observed_at=datetime.now(UTC).isoformat(),
    )


def response(s, statement="喜欢天文", key="interest:天文", certainty="EXPLICIT"):
    return ExtractionResponse(
        request_id="test",
        facts=[
            dict(
                key=key,
                category="INTEREST",
                statement=statement,
                source_message_id=s.id,
                quote=s.text,
                certainty=certainty,
                valid_until=None,
            )
        ],
    )


@pytest.mark.asyncio
async def test_auto_update_does_not_invalidate_chat_and_manual_edit_wins(
    content_session, test_settings
):
    db = content_session
    user = await student(test_settings)
    await state_for(db, user.id)
    s = source()
    assert await apply_extraction(db, user.id, response(s), [s]) == 1
    await db.commit()
    assert await get_memory_context_revision(db, owner_user_id=user.id) == 0
    item = await db.scalar(select(PersonalMemoryItem))
    await item_action(
        db, user.id, item.id, base_revision=1, action="EDIT", statement="现在更喜欢生物"
    )
    assert await get_memory_context_revision(db, owner_user_id=user.id) > 0
    assert await apply_extraction(db, user.id, response(source()), [s]) == 0
    new = source("我喜欢天文。")
    assert await apply_extraction(db, user.id, response(new), [new]) == 0
    assert item.statement == "现在更喜欢生物"


@pytest.mark.asyncio
async def test_forget_blocks_replay_and_owner_context(content_session, test_settings):
    db = content_session
    user = await student(test_settings)
    other = await student(test_settings, "auto.other")
    s = source()
    await apply_extraction(db, user.id, response(s), [s])
    await db.commit()
    item = await db.scalar(select(PersonalMemoryItem))
    assert await KeywordMemoryRetriever().retrieve(db, other.id, "天文") == []
    item_id = item.id
    with pytest.raises(LookupError):
        await item_action(db, other.id, item.id, base_revision=1, action="FORGET")
    await db.rollback()
    await item_action(db, user.id, item_id, base_revision=1, action="FORGET")
    assert await apply_extraction(db, user.id, response(s), [s]) == 0
    assert await KeywordMemoryRetriever().retrieve(db, user.id, "天文") == []


@pytest.mark.asyncio
async def test_rejects_sensitive_hypothetical_and_invalid_sources(content_session, test_settings):
    db = content_session
    user = await student(test_settings)
    for text in ["假如我喜欢天文。", "我喜欢天文，密码是 ABC。"]:
        s = source(text)
        assert await apply_extraction(db, user.id, response(s), [s]) == 0
    s = source()
    assert await apply_extraction(db, user.id, response(s), []) == 0
    uncertain = response(s, certainty="UNCERTAIN")
    await apply_extraction(db, user.id, uncertain, [s])
    await db.commit()
    assert await KeywordMemoryRetriever().retrieve(db, user.id, "天文") == []


@pytest.mark.asyncio
async def test_duplicate_and_older_backfill_do_not_overwrite_current(
    content_session, test_settings
):
    db = content_session
    user = await student(test_settings)
    s = source()
    assert await apply_extraction(db, user.id, response(s), [s]) == 1
    assert await apply_extraction(db, user.id, response(s), [s]) == 0
    old = source("我喜欢物理。")
    old.observed_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    assert await apply_extraction(db, user.id, response(old, "喜欢物理"), [old]) == 0
    item = await db.scalar(select(PersonalMemoryItem))
    assert item.statement == "喜欢天文"


@pytest.mark.asyncio
async def test_durable_worker_and_backfill_are_idempotent(content_session, test_settings):
    db = content_session
    settings = test_settings.model_copy(
        update={"gateway_mode": "fixture", "memory_coalesce_seconds": 0}
    )
    user = await student(settings)
    session = await create_free_session(db, settings=settings, user=user)
    run, _ = await create_turn(
        db,
        user=user,
        session=session,
        operation="TEACH_TURN",
        message="我喜欢天文。",
        idempotency_key="auto-worker-1",
    )
    run.status = "SUCCEEDED"
    await enqueue_run(db, run, immediate=True)
    await enqueue_run(db, run, immediate=True)
    await db.commit()
    assert await run_once(settings) == 1
    assert await run_once(settings) == 0
    session_id = session.id
    db.expire_all()
    item = await db.scalar(select(PersonalMemoryItem))
    assert item.statement == "喜欢天文"
    await history_backfill(db, user.id, [session_id])
    assert await run_once(settings) == 0
    tasks = list(await db.scalars(select(MemoryTask)))
    assert len(tasks) == 1 and tasks[0].status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_late_extraction_cannot_resurrect_after_disable(content_session, test_settings):
    db = content_session
    settings = test_settings.model_copy(update={"gateway_mode": "fixture"})
    user = await student(settings)
    session = await create_free_session(db, settings=settings, user=user)
    run, _ = await create_turn(
        db,
        user=user,
        session=session,
        operation="TEACH_TURN",
        message="我喜欢天文。",
        idempotency_key="auto-late-1",
    )
    run.status = "SUCCEEDED"
    await enqueue_run(db, run, immediate=True)
    await db.commit()

    async def delayed(settings, payload, target):
        await settings_update(db, user.id, 1, False, False)
        return response(payload.sources[0])

    await run_once(settings, extractor=delayed)
    assert await db.scalar(select(PersonalMemoryItem)) is None


@pytest.mark.asyncio
async def test_chat_delete_keep_and_forget(content_session, test_settings):
    db = content_session
    user = await student(test_settings)
    s = source()
    await apply_extraction(db, user.id, response(s), [s])
    await db.commit()
    await delete_chat_memory(db, user.id, uuid.UUID(s.session_id), False)
    row = await db.scalar(select(PersonalMemoryItem))
    assert row.status == "ACTIVE" and row.sources[0]["deleted"]
    await delete_chat_memory(db, user.id, uuid.UUID(s.session_id), True)
    assert row.status == "REMOVED"


@pytest.mark.asyncio
async def test_registry_routes_and_pinned_teacher_configuration(content_session, test_settings):
    data = initial_data(test_settings)
    for a in data["agents"]:
        if a["id"] in ("primary", "junior"):
            a.update(
                enabled=True,
                bot_id="bot-" + a["id"],
                workspace_id="workspace",
                remote_memory_disabled=True,
            )
    data["routes"] = [
        dict(operation="TEACH_TURN", stage="PRIMARY_LOWER", agent_id="primary"),
        dict(operation="TEACH_TURN", stage="JUNIOR", agent_id="junior"),
    ]
    RegistryData.model_validate(data)
    content_session.add(AIConfiguration(id=1, revision=1, data=data))
    await content_session.commit()
    primary = await resolve(content_session, "TEACH_TURN", "PRIMARY_LOWER")
    junior = await resolve(content_session, "TEACH_TURN", "JUNIOR")
    assert primary["bot_id"] != junior["bot_id"]
    assert (await resolve(content_session, "TEACH_TURN", "JUNIOR", primary))["id"] == "primary"
    data["routes"].append(data["routes"][0])
    with pytest.raises(ValueError):
        RegistryData.model_validate(data)


@pytest.mark.asyncio
async def test_admin_configuration_and_memory_http_ownership(
    client, content_session, test_settings
):
    from app.modules.identity.models import UserRole
    from tests.identity_helpers import auth_headers, csrf, login

    await student(test_settings, "auto.http.student")
    await login(client, "auto.http.student", "synthetic-pass-1")
    assert (await client.get("/api/v1/admin/ai/configuration")).status_code == 403
    initial = await client.get("/api/v1/growth/personal-memory")
    assert initial.status_code == 200 and initial.json()["settings"]["auto_enabled"]
    token = await csrf(client)
    changed = await client.patch(
        "/api/v1/growth/personal-memory/settings",
        json={"base_revision": 1, "auto_enabled": True, "use_enabled": False},
        headers=auth_headers(token),
    )
    assert changed.status_code == 200 and not changed.json()["settings"]["use_enabled"]
    stale = await client.patch(
        "/api/v1/growth/personal-memory/settings",
        json={"base_revision": 1, "auto_enabled": True, "use_enabled": True},
        headers=auth_headers(token),
    )
    assert stale.status_code == 409
    await client.post("/api/v1/auth/logout", headers=auth_headers(token))
    await create_synthetic_user(
        test_settings,
        username="auto.http.admin",
        password="synthetic-pass-1",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    await login(client, "auto.http.admin", "synthetic-pass-1")
    config = (await client.get("/api/v1/admin/ai/configuration")).json()
    token = await csrf(client)
    saved = await client.put(
        "/api/v1/admin/ai/configuration",
        json={"base_revision": config["revision"], "data": config["data"]},
        headers=auth_headers(token),
    )
    assert saved.status_code == 200
    assert "PAT" not in saved.text
    assert (await client.get("/api/v1/growth/personal-memory")).status_code == 403
    prompt = await client.get("/api/v1/admin/ai/agents/primary/prompt-template")
    assert prompt.status_code == 200 and "小学教师" in prompt.json()["prompt"]


@pytest.mark.asyncio
async def test_worker_claims_an_account_once(content_session, test_settings):
    import asyncio

    db = content_session
    settings = test_settings.model_copy(
        update={"gateway_mode": "fixture", "memory_coalesce_seconds": 0}
    )
    user = await student(settings, "auto.concurrent")
    session = await create_free_session(db, settings=settings, user=user)
    run, _ = await create_turn(
        db,
        user=user,
        session=session,
        operation="TEACH_TURN",
        message="我喜欢画画。",
        idempotency_key="auto-concurrent",
    )
    run.status = "SUCCEEDED"
    await enqueue_run(db, run, immediate=True)
    await db.commit()
    assert sum(await asyncio.gather(run_once(settings), run_once(settings))) == 1
    assert len(list(await db.scalars(select(PersonalMemoryItem)))) == 1


def test_database_targets_do_not_require_legacy_environment_ids(test_settings, monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("KNODO_PAT", "synthetic-test-token")
    values = test_settings.model_dump()
    values.update(
        gateway_mode="knodo",
        knodo_base_url="https://knodo.vip",
        knodo_tutor_bot_id=None,
        knodo_tutor_workspace_id=None,
        knodo_designer_bot_id=None,
        knodo_designer_workspace_id=None,
    )
    settings = Settings(**values)
    assert settings.knodo_tutor_bot_id is None
