from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import Settings
from app.modules.content.importer import import_package
from app.modules.content.models import ChapterRevision, ReviewStatus
from app.modules.content.package import load_package
from app.modules.content.service import publish_revision, record_review
from tests.content_helpers import (
    FIXTURE_PACKAGE,
    LEGACY_PACKAGE,
    edit_json,
    revision_by_slug,
)
from tests.identity_helpers import create_synthetic_user, csrf, login, write_headers


async def _user(settings: Settings, username: str, stage: str, grade: int | None):
    return await create_synthetic_user(
        settings, username=username, password="synthetic-pass-1", stage=stage, grade=grade
    )


async def _headers(client) -> dict[str, str]:
    """Origin + CSRF headers for content writes (T05 middleware applies)."""

    return write_headers(await csrf(client))


async def _body_of(session, revision_id) -> list[dict]:
    body = await session.scalar(
        select(ChapterRevision.body).where(ChapterRevision.id == revision_id)
    )
    return list(body)


@pytest.mark.asyncio
async def test_page_context_uses_authoritative_revision(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _user(test_settings, "ctx.junior", "JUNIOR", 8)
    await login(client, "ctx.junior", "synthetic-pass-1")

    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert revision is not None
    body = await _body_of(content_session, revision.id)
    paragraph = body[2]["text"]

    ok = await client.post(
        "/api/v1/content/page-context",
        headers=await _headers(client),
        json={
            "chapter_id": str(revision.chapter_id),
            "revision": 1,
            "block_id": "b3",
            "selected_text": f"  {paragraph[:12]}\n",
        },
    )
    assert ok.status_code == 200, ok.text
    context = ok.json()
    assert context["source_id"] == f"chapter:{revision.chapter_id}"
    assert context["revision"] == 1
    assert context["block_id"] == "b3"
    assert context["selected_text"] == paragraph[:12].strip()
    assert context["selected_text_chars"] == len(paragraph[:12].strip())

    forged = await client.post(
        "/api/v1/content/page-context",
        headers=await _headers(client),
        json={
            "chapter_id": str(revision.chapter_id),
            "revision": 1,
            "block_id": "b3",
            "selected_text": "这段文字不在权威正文里，必须被拒绝",
        },
    )
    assert forged.status_code == 422
    assert forged.json()["error"]["message"] == "选中文字与权威正文不一致"

    unknown_block = await client.post(
        "/api/v1/content/page-context",
        headers=await _headers(client),
        json={
            "chapter_id": str(revision.chapter_id),
            "revision": 1,
            "block_id": "b99",
            "selected_text": paragraph[:8],
        },
    )
    assert unknown_block.status_code == 422
    assert unknown_block.json()["error"]["message"] == "章节中不存在该小节或内容块"

    stale_revision = await client.post(
        "/api/v1/content/page-context",
        headers=await _headers(client),
        json={
            "chapter_id": str(revision.chapter_id),
            "revision": 99,
            "selected_text": paragraph[:8],
        },
    )
    assert stale_revision.status_code == 404


@pytest.mark.asyncio
async def test_page_context_requires_same_origin_and_csrf(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _user(test_settings, "ctx.csrf", "JUNIOR", 8)
    await login(client, "ctx.csrf", "synthetic-pass-1")
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert revision is not None

    without_csrf = await client.post(
        "/api/v1/content/page-context",
        json={"chapter_id": str(revision.chapter_id), "revision": 1},
    )
    assert without_csrf.status_code == 403


@pytest.mark.asyncio
async def test_page_context_rejects_cross_stage_chapter(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _user(test_settings, "ctx.lower", "PRIMARY_LOWER", 2)
    await login(client, "ctx.lower", "synthetic-pass-1")
    junior = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert junior is not None

    response = await client.post(
        "/api/v1/content/page-context",
        headers=await _headers(client),
        json={"chapter_id": str(junior.chapter_id), "revision": 1},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reading_state_is_owner_scoped_and_revision_aware(
    content_session, client, test_settings, tmp_path: Path
):
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    await _user(test_settings, "state.a", "JUNIOR", 8)
    await _user(test_settings, "state.b", "JUNIOR", 8)

    first = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert first is not None
    await record_review(
        content_session,
        revision_id=first.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    await publish_revision(content_session, revision_id=first.id, actor="合成测试发布者")
    body = await _body_of(content_session, first.id)
    paragraph = next(block["text"] for block in body if block["type"] == "PARAGRAPH")

    await login(client, "state.a", "synthetic-pass-1")
    entered = await client.post(
        "/api/v1/reading-events",
        headers=await _headers(client),
        json={
            "client_event_id": "state-a-enter-01",
            "chapter_id": str(first.chapter_id),
            "revision": 1,
            "event_kind": "ENTER",
        },
    )
    assert entered.status_code == 200, entered.text
    selected = await client.post(
        "/api/v1/reading-events",
        headers=await _headers(client),
        json={
            "client_event_id": "state-a-select-01",
            "chapter_id": str(first.chapter_id),
            "revision": 1,
            "event_kind": "SELECT_TEXT",
            "block_id": "b3",
            "selected_text_length": len(paragraph[:12].strip()),
        },
    )
    assert selected.status_code == 200, selected.text

    state_a = await client.get(f"/api/v1/chapters/{first.chapter_id}/reading-state")
    assert state_a.status_code == 200
    assert state_a.json()["event_kind"] == "SELECT_TEXT"
    assert state_a.json()["block_id"] == "b3"
    assert state_a.json()["is_current_revision"] is True

    # Another student never sees A's position.
    await login(client, "state.b", "synthetic-pass-1")
    state_b = await client.get(f"/api/v1/chapters/{first.chapter_id}/reading-state")
    assert state_b.status_code == 200
    assert state_b.json() is None

    # Publish a newer revision of the same chapter: A's saved position belongs
    # to r1 and must be reported as a stale revision, not silently re-used.
    revised = tmp_path / "revised"
    shutil.copytree(LEGACY_PACKAGE, revised)
    edit_json(
        revised / "release.json",
        lambda data: data.__setitem__("release_key", "legacy-k12-696364f-r2"),
    )

    def bump(data: dict) -> None:
        chapter = next(item for item in data["chapters"] if item["stable_slug"] == "ch05")
        chapter["revision"] = 2

    edit_json(revised / "courses/python-first-steps/course.json", bump)
    chapter_path = revised / "courses/python-first-steps/chapters/ch05.json"
    document = json.loads(chapter_path.read_text(encoding="utf-8"))
    document["revision"] = 2
    document["blocks"][0]["text"] = "小项目：猜数字游戏（第二版）"
    chapter_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    await import_package(content_session, load_package(revised), dry_run=False)
    second = await revision_by_slug(content_session, "python-first-steps", "ch05", 2)
    assert second is not None
    await record_review(
        content_session,
        revision_id=second.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    await publish_revision(content_session, revision_id=second.id, actor="合成测试发布者")

    await login(client, "state.a", "synthetic-pass-1")
    state_after = await client.get(f"/api/v1/chapters/{first.chapter_id}/reading-state")
    assert state_after.status_code == 200
    assert state_after.json()["revision"] == 1
    assert state_after.json()["is_current_revision"] is False
    current = await client.get(f"/api/v1/chapters/{first.chapter_id}")
    assert current.status_code == 200
    assert current.json()["revision"] == 2
