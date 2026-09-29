from __future__ import annotations

import pytest

from app.modules.content.importer import import_package
from app.modules.content.package import load_package
from tests.content_helpers import FIXTURE_PACKAGE, revision_by_slug
from tests.identity_helpers import create_synthetic_user
from tests.teaching_helpers import create_app_client, csrf_headers, login, teaching_settings


@pytest.mark.asyncio
async def test_catalogue_and_bookshelf_are_owner_scoped(content_session, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    user = await create_synthetic_user(
        test_settings,
        username="learning.catalog.student",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=8,
    )
    settings = teaching_settings(test_settings)
    async with create_app_client(settings) as client:
        assert (await login(client, user.username, "synthetic-pass-1")).status_code == 200
        catalogue = await client.get("/api/v1/learning/catalog", params={"kind": "COURSE"})
        assert catalogue.status_code == 200, catalogue.text
        items = catalogue.json()["items"]
        assert [item["title"] for item in items] == ["T06 合成夹具课程（非教学）"]
        course_id = items[0]["id"]

        headers = await csrf_headers(client)
        first = await client.put(f"/api/v1/learning/bookshelf/COURSE/{course_id}", headers=headers)
        second = await client.put(f"/api/v1/learning/bookshelf/COURSE/{course_id}", headers=headers)
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        shelf = await client.get("/api/v1/learning/bookshelf")
        assert shelf.status_code == 200
        assert shelf.json()["total"] == 1
        assert shelf.json()["items"][0]["available"] is True

        removed = await client.delete(
            f"/api/v1/learning/bookshelf/COURSE/{course_id}", headers=headers
        )
        assert removed.status_code == 200
        assert removed.json() == {"deleted": True}
        assert (await client.get("/api/v1/learning/bookshelf")).json()["total"] == 0


@pytest.mark.asyncio
async def test_continue_ignores_locationless_leave_after_block_view(content_session, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    user = await create_synthetic_user(
        test_settings,
        username="learning.continue.student",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=8,
    )
    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert chapter is not None
    settings = teaching_settings(test_settings)
    async with create_app_client(settings) as client:
        assert (await login(client, user.username, "synthetic-pass-1")).status_code == 200
        headers = await csrf_headers(client)
        enter = await client.post(
            "/api/v1/reading-events",
            json={
                "client_event_id": "learning-enter-01",
                "chapter_id": str(chapter.chapter_id),
                "revision": 1,
                "event_kind": "ENTER",
            },
            headers=headers,
        )
        block = await client.post(
            "/api/v1/reading-events",
            json={
                "client_event_id": "learning-block-01",
                "chapter_id": str(chapter.chapter_id),
                "revision": 1,
                "event_kind": "BLOCK_VIEW",
                "block_id": "b1",
            },
            headers=headers,
        )
        leave = await client.post(
            "/api/v1/reading-events",
            json={
                "client_event_id": "learning-leave-01",
                "chapter_id": str(chapter.chapter_id),
                "revision": 1,
                "event_kind": "LEAVE",
            },
            headers=headers,
        )
        assert enter.status_code == block.status_code == leave.status_code == 200

        state = await client.get(f"/api/v1/chapters/{chapter.chapter_id}/reading-state")
        assert state.status_code == 200, state.text
        assert state.json()["event_kind"] == "BLOCK_VIEW"
        assert state.json()["block_id"] == "b1"

        continuation = await client.get("/api/v1/learning/continue")
        assert continuation.status_code == 200, continuation.text
        assert continuation.json()["item"]["block_id"] == "b1"

        history = await client.get("/api/v1/learning/history", params={"kind": "READING"})
        assert history.status_code == 200
        assert history.json()["total"] == 1
        assert history.json()["items"][0]["event_kind"] == "BLOCK_VIEW"


@pytest.mark.asyncio
async def test_catalogue_requires_a_student_session(client):
    response = await client.get("/api/v1/learning/catalog")
    assert response.status_code == 401
