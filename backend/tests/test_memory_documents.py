"""Student-owned Markdown memory documents and AI-use revocation."""

from __future__ import annotations

import pytest

from app.modules.learning.projection import merge_learner_context
from app.modules.memory.models import MemoryContextState
from app.modules.memory.service import build_learner_context, get_memory_context_revision
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import csrf_headers

PASSWORD = "synthetic-pass-1"


def test_primary_note_is_not_crowded_out_by_a_full_evidence_list():
    context = {
        "evidence": [
            {"id": f"quiz:{number}", "kind": "QUIZ_RESULT", "summary": "已完成练习"}
            for number in range(12)
        ],
        "allowed_evidence_ids": [],
    }
    note = {
        "id": "memory-document:owned:v4",
        "kind": "CONFIRMED_MEMORY",
        "summary": "学生本人写下的学习偏好",
    }
    result = merge_learner_context(context, [note])
    assert len(result) == 12
    assert result[0] == note
    assert note["id"] in context["allowed_evidence_ids"]


@pytest.mark.asyncio
async def test_document_crud_versions_conflict_and_restore(client, test_settings, content_session):
    user = await create_synthetic_user(
        test_settings, username="t18.docs-crud", password=PASSWORD, stage="JUNIOR", grade=8
    )
    assert (await login(client, user.username, PASSWORD)).status_code == 200

    created = await client.post(
        "/api/v1/growth/documents",
        json={"title": "学习偏好", "category": "PREFERENCE", "content_markdown": "喜欢示例"},
        headers=await csrf_headers(client),
    )
    assert created.status_code == 200, created.text
    document = created.json()
    assert document["revision"] == 1
    assert document["ai_enabled"] is False
    assert len(document["versions"]) == 1

    edited = await client.patch(
        f"/api/v1/growth/documents/{document['id']}",
        json={"base_revision": 1, "content_markdown": "喜欢通过小例子理解概念"},
        headers=await csrf_headers(client),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2

    conflict = await client.patch(
        f"/api/v1/growth/documents/{document['id']}",
        json={"base_revision": 1, "content_markdown": "过期写入"},
        headers=await csrf_headers(client),
    )
    assert conflict.status_code == 409

    restored = await client.post(
        f"/api/v1/growth/documents/{document['id']}/restore",
        json={"version_revision": 1, "base_revision": 2},
        headers=await csrf_headers(client),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["revision"] == 3
    assert restored.json()["content_markdown"] == "喜欢示例"

    versions = await client.get(f"/api/v1/growth/documents/{document['id']}/versions")
    assert versions.status_code == 200
    assert [item["revision"] for item in versions.json()["items"]] == [3, 2, 1]
    previous = await client.get(f"/api/v1/growth/documents/{document['id']}/versions/2")
    assert previous.status_code == 200
    assert previous.json()["content_markdown"] == "喜欢通过小例子理解概念"
    assert versions.json()["items"][0]["action"] == "RESTORE"


@pytest.mark.asyncio
async def test_document_ai_opt_in_is_bounded_and_revision_changes_on_revoke(
    client, test_settings, content_session
):
    user = await create_synthetic_user(
        test_settings, username="t18.docs-context", password=PASSWORD, stage="JUNIOR", grade=8
    )
    assert (await login(client, user.username, PASSWORD)).status_code == 200

    created = await client.post(
        "/api/v1/growth/documents",
        json={
            "title": "辅导笔记",
            "category": "NOTE",
            "content_markdown": "只在授权后用于辅导",
        },
        headers=await csrf_headers(client),
    )
    assert created.status_code == 200
    document = created.json()
    assert await get_memory_context_revision(content_session, owner_user_id=user.id) == 0
    before = await build_learner_context(content_session, owner_user_id=user.id)
    assert all("辅导笔记" not in item.get("summary", "") for item in before)

    enabled = await client.patch(
        f"/api/v1/growth/documents/{document['id']}",
        json={"base_revision": 1, "ai_enabled": True},
        headers=await csrf_headers(client),
    )
    assert enabled.status_code == 200, enabled.text
    assert await get_memory_context_revision(content_session, owner_user_id=user.id) == 1
    context = await build_learner_context(content_session, owner_user_id=user.id, memory_limit=4)
    personal = [item for item in context if item["id"].startswith("memory-document:")]
    assert len(personal) == 1
    assert personal[0]["kind"] == "CONFIRMED_MEMORY"
    assert "只在授权后" in personal[0]["summary"]

    disabled = await client.patch(
        f"/api/v1/growth/documents/{document['id']}",
        json={"base_revision": 2, "ai_enabled": False},
        headers=await csrf_headers(client),
    )
    assert disabled.status_code == 200, disabled.text
    assert await get_memory_context_revision(content_session, owner_user_id=user.id) == 2
    context = await build_learner_context(content_session, owner_user_id=user.id, memory_limit=4)
    assert all(not item["id"].startswith("memory-document:") for item in context)

    state = await content_session.get(MemoryContextState, user.id)
    assert state is not None and state.revision == 2


@pytest.mark.asyncio
async def test_documents_are_owner_scoped(client, test_settings):
    owner = await create_synthetic_user(
        test_settings, username="t18.docs-owner", password=PASSWORD, stage="JUNIOR", grade=8
    )
    other = await create_synthetic_user(
        test_settings, username="t18.docs-other", password=PASSWORD, stage="JUNIOR", grade=8
    )
    assert (await login(client, owner.username, PASSWORD)).status_code == 200
    created = await client.post(
        "/api/v1/growth/documents",
        json={"title": "私人笔记", "content_markdown": "仅本人可读"},
        headers=await csrf_headers(client),
    )
    document_id = created.json()["id"]

    # A second client gets a separate session and must not read or mutate it.
    from tests.teaching_helpers import create_app_client, teaching_settings

    async with create_app_client(teaching_settings(test_settings)) as other_client:
        assert (await login(other_client, other.username, PASSWORD)).status_code == 200
        hidden = await other_client.get(f"/api/v1/growth/documents/{document_id}")
        assert hidden.status_code == 404
        assert (
            await other_client.get(f"/api/v1/growth/documents/{document_id}/versions")
        ).status_code == 404
        assert (
            await other_client.get(f"/api/v1/growth/documents/{document_id}/versions/1")
        ).status_code == 404
        hidden_restore = await other_client.post(
            f"/api/v1/growth/documents/{document_id}/restore",
            json={"version_revision": 1, "base_revision": 1},
            headers=await csrf_headers(other_client),
        )
        assert hidden_restore.status_code == 404
        hidden_delete = await other_client.delete(
            f"/api/v1/growth/documents/{document_id}",
            headers=await csrf_headers(other_client),
        )
        assert hidden_delete.status_code == 404


@pytest.mark.asyncio
async def test_primary_document_is_idempotent_and_account_scoped(
    client, test_settings, content_session
):
    user = await create_synthetic_user(
        test_settings,
        username="t18.docs-primary",
        password=PASSWORD,
        stage="PRIMARY_LOWER",
        grade=2,
    )
    assert (await login(client, user.username, PASSWORD)).status_code == 200
    payload = {
        "title": "个人记忆.md",
        "category": "NOTE",
        "content_markdown": "",
        "is_primary": True,
    }
    first = await client.post(
        "/api/v1/growth/documents", json=payload, headers=await csrf_headers(client)
    )
    second = await client.post(
        "/api/v1/growth/documents", json=payload, headers=await csrf_headers(client)
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["is_primary"] is True
    assert first.json()["ai_enabled"] is True
    assert await get_memory_context_revision(content_session, owner_user_id=user.id) == 1
    edited = await client.patch(
        f"/api/v1/growth/documents/{first.json()['id']}",
        json={"base_revision": 1, "content_markdown": "我喜欢用画图理解分数。"},
        headers=await csrf_headers(client),
    )
    assert edited.status_code == 200, edited.text
    assert await get_memory_context_revision(content_session, owner_user_id=user.id) == 2
    context = await build_learner_context(content_session, owner_user_id=user.id, memory_limit=1)
    assert len(context) == 1
    assert "画图理解分数" in context[0]["summary"]
    assert f":v{edited.json()['revision']}" in context[0]["id"]
    disabled = await client.patch(
        f"/api/v1/growth/documents/{first.json()['id']}",
        json={"base_revision": edited.json()["revision"], "ai_enabled": False},
        headers=await csrf_headers(client),
    )
    assert disabled.status_code == 422
    assert await get_memory_context_revision(content_session, owner_user_id=user.id) == 2
    restored = await client.post(
        f"/api/v1/growth/documents/{first.json()['id']}/restore",
        json={"version_revision": 1, "base_revision": edited.json()["revision"]},
        headers=await csrf_headers(client),
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["ai_enabled"] is True
    assert restored.json()["content_markdown"] == ""
    assert await get_memory_context_revision(content_session, owner_user_id=user.id) == 3
    assert all(
        not item["id"].startswith("memory-document:")
        for item in await build_learner_context(content_session, owner_user_id=user.id)
    )
    listed = (await client.get("/api/v1/growth/documents")).json()["items"]
    assert len(listed) == 1
