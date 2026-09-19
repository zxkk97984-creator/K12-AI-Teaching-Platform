from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from app.config import Settings
from app.modules.content.importer import import_package
from app.modules.content.models import ReadingEvent, ReviewStatus
from app.modules.content.package import load_package
from app.modules.content.service import publish_revision, record_review
from tests.content_helpers import FIXTURE_PACKAGE, LEGACY_PACKAGE, revision_by_slug, table_counts
from tests.identity_helpers import create_synthetic_user, csrf, login, write_headers


async def _headers(client) -> dict[str, str]:
    """Origin + CSRF headers for content writes (T05 middleware applies)."""

    return write_headers(await csrf(client))


async def _user(settings: Settings, username: str):
    return await create_synthetic_user(
        settings, username=username, password="synthetic-pass-1", stage="JUNIOR", grade=8
    )


@pytest.mark.asyncio
async def test_reading_event_is_idempotent_per_client_id(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _user(test_settings, "evt.a")
    await login(client, "evt.a", "synthetic-pass-1")
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert revision is not None

    payload = {
        "client_event_id": "evt-repeat-0001",
        "chapter_id": str(revision.chapter_id),
        "revision": 1,
        "event_kind": "ENTER",
    }
    first = await client.post(
        "/api/v1/reading-events", json=payload, headers=await _headers(client)
    )
    second = await client.post(
        "/api/v1/reading-events", json=payload, headers=await _headers(client)
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["event_id"] == second.json()["event_id"]

    total = await content_session.scalar(select(func.count()).select_from(ReadingEvent))
    assert total == 1


@pytest.mark.asyncio
async def test_reading_events_are_owner_scoped(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _user(test_settings, "evt.owner.a")
    await _user(test_settings, "evt.owner.b")
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert revision is not None

    same_client_id = {
        "client_event_id": "evt-shared-0001",
        "chapter_id": str(revision.chapter_id),
        "revision": 1,
        "event_kind": "ENTER",
    }
    await login(client, "evt.owner.a", "synthetic-pass-1")
    a = await client.post(
        "/api/v1/reading-events", json=same_client_id, headers=await _headers(client)
    )
    await login(client, "evt.owner.b", "synthetic-pass-1")
    b = await client.post(
        "/api/v1/reading-events", json=same_client_id, headers=await _headers(client)
    )
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["duplicate"] is False and b.json()["duplicate"] is False
    assert a.json()["event_id"] != b.json()["event_id"]

    total = await content_session.scalar(select(func.count()).select_from(ReadingEvent))
    assert total == 2


@pytest.mark.asyncio
async def test_invalid_event_payloads_are_rejected(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _user(test_settings, "evt.invalid")
    await login(client, "evt.invalid", "synthetic-pass-1")
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert revision is not None
    base = {"chapter_id": str(revision.chapter_id), "revision": 1}

    cases = [
        {**base, "client_event_id": "evt-select-nolen", "event_kind": "SELECT_TEXT"},
        {
            **base,
            "client_event_id": "evt-enter-withlen",
            "event_kind": "ENTER",
            "selected_text_length": 5,
        },
        {**base, "client_event_id": "evt-bad-kind", "event_kind": "READ_EVERYTHING"},
        {**base, "client_event_id": "short", "event_kind": "ENTER"},
        {
            **base,
            "client_event_id": "evt-bad-block-1",
            "event_kind": "BLOCK_VIEW",
            "block_id": "b99",
        },
    ]
    for payload in cases:
        response = await client.post(
            "/api/v1/reading-events", json=payload, headers=await _headers(client)
        )
        assert response.status_code == 422, payload

    total = await content_session.scalar(select(func.count()).select_from(ReadingEvent))
    assert total == 0


@pytest.mark.asyncio
async def test_unpublished_chapter_cannot_receive_events(content_session, client, test_settings):
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    await _user(test_settings, "evt.draft")
    await login(client, "evt.draft", "synthetic-pass-1")
    draft = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert draft is not None

    response = await client.post(
        "/api/v1/reading-events",
        headers=await _headers(client),
        json={
            "client_event_id": "evt-draft-0001",
            "chapter_id": str(draft.chapter_id),
            "revision": 1,
            "event_kind": "ENTER",
        },
    )
    assert response.status_code == 404
    assert await content_session.scalar(select(func.count()).select_from(ReadingEvent)) == 0


@pytest.mark.asyncio
async def test_reading_events_store_behaviour_only(content_session, client, test_settings):
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    await _user(test_settings, "evt.columns")
    await login(client, "evt.columns", "synthetic-pass-1")
    revision = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert revision is not None
    await record_review(
        content_session,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    await publish_revision(content_session, revision_id=revision.id, actor="合成测试发布者")

    posted = await client.post(
        "/api/v1/reading-events",
        headers=await _headers(client),
        json={
            "client_event_id": "evt-select-0001",
            "chapter_id": str(revision.chapter_id),
            "revision": 1,
            "event_kind": "SELECT_TEXT",
            "block_id": "b2",
            "selected_text_length": 12,
        },
    )
    assert posted.status_code == 200, posted.text

    columns = (
        await content_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'content_reading_events'"
            )
        )
    ).scalars()
    names = {name.lower() for name in columns}
    for forbidden in (
        "mastery",
        "percentage",
        "percent",
        "score",
        "completed",
        "progress",
        "answer",
    ):
        assert forbidden not in names
    # The selected text itself is never stored, only its length.
    assert "selected_text" not in names
    assert "selected_text_length" in names
    event = await content_session.scalar(select(ReadingEvent))
    assert event is not None
    assert event.event_kind == "SELECT_TEXT"
    assert event.selected_text_length == 12
    counts = await table_counts(content_session)
    assert counts["content_reading_events"] == 1
