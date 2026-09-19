from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import Settings
from app.modules.content.importer import import_package
from app.modules.content.models import ReviewStatus
from app.modules.content.package import load_package
from app.modules.content.service import publish_revision, record_review, withdraw_revision
from tests.content_helpers import (
    FIXTURE_PACKAGE,
    LEGACY_PACKAGE,
    revision_by_slug,
)
from tests.identity_helpers import create_synthetic_user, login


async def _junior(settings: Settings, username: str = "content.junior"):
    return await create_synthetic_user(
        settings, username=username, password="synthetic-pass-1", stage="JUNIOR", grade=8
    )


async def _lower(settings: Settings, username: str = "content.lower"):
    return await create_synthetic_user(
        settings,
        username=username,
        password="synthetic-pass-1",
        stage="PRIMARY_LOWER",
        grade=2,
    )


@pytest.mark.asyncio
async def test_catalogue_only_shows_readable_chapters(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    await _junior(test_settings)

    response = await login(client, "content.junior", "synthetic-pass-1")
    assert response.status_code == 200, response.text
    listing = await client.get("/api/v1/courses")
    assert listing.status_code == 200, listing.text
    slugs = [item["slug"] for item in listing.json()["items"]]
    # The fixture course has a JUNIOR chapter (no grade range => stage-only match).
    # The legacy chapters stay DRAFT, so they must not appear.
    assert slugs == ["t06-fixture-course"]
    assert "python-first-steps" not in slugs

    course_id = listing.json()["items"][0]["course_id"]
    detail = await client.get(f"/api/v1/courses/{course_id}")
    assert detail.status_code == 200
    chapters = [chapter["chapter_slug"] for chapter in detail.json()["chapters"]]
    assert chapters == ["ch02"]


@pytest.mark.asyncio
async def test_fixture_is_labelled_and_formal_profile_hides_it(
    content_session, client, test_settings
):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _lower(test_settings, "content.lower.fixture")
    await login(client, "content.lower.fixture", "synthetic-pass-1")

    listing = await client.get("/api/v1/courses")
    item = listing.json()["items"][0]
    chapter = item["chapters"][0]
    assert chapter["is_test_fixture"] is True
    assert chapter["content_notice"] == "测试内容，未作人工教学审校"

    # Formal profile (production semantics) must not serve fixtures at all.
    # APP_ENV=production is the only formal runtime profile, so the formal
    # viewer scope is asserted directly here instead of weakening the gate.
    from app.modules.content.models import ContentProfile
    from app.modules.content.schemas import ViewerScope
    from app.modules.content.service import visible_chapters

    formal_viewer = ViewerScope(stage="PRIMARY_LOWER", grade=2, profile=ContentProfile.FORMAL)
    assert await visible_chapters(content_session, formal_viewer) == []


@pytest.mark.asyncio
async def test_detail_rejects_unpublished_wrong_stage_and_unknown_ids(
    content_session, client, test_settings
):
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    await _junior(test_settings, "content.junior.detail")
    await login(client, "content.junior.detail", "synthetic-pass-1")

    junior = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    senior = await revision_by_slug(content_session, "algorithm-everyday", "ch03", 1)
    assert junior is not None and senior is not None

    responses = [
        await client.get(f"/api/v1/chapters/{junior.chapter_id}"),  # DRAFT
        await client.get(f"/api/v1/chapters/{senior.chapter_id}"),  # wrong stage
        await client.get(f"/api/v1/chapters/{uuid.uuid4()}"),  # unknown
    ]
    for response in responses:
        assert response.status_code == 404
    bodies = [response.json()["error"] for response in responses]
    assert {body["message"] for body in bodies} == {"章节不可用"}
    assert {body["code"] for body in bodies} == {"NOT_FOUND"}


@pytest.mark.asyncio
async def test_published_chapter_payload_and_withdrawal(content_session, client, test_settings):
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    await _junior(test_settings, "content.junior.read")
    await login(client, "content.junior.read", "synthetic-pass-1")

    revision = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert revision is not None
    await record_review(
        content_session,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    await publish_revision(content_session, revision_id=revision.id, actor="合成测试发布者")

    detail = await client.get(f"/api/v1/chapters/{revision.chapter_id}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()

    assert payload["revision"] == 1
    assert payload["blocks"][0]["block_id"] == "b1"
    assert payload["blocks"][0]["type"] == "TITLE"
    assert payload["objectives"]
    assert payload["source"]["source_commit"].startswith("696364f")
    assert set(payload["source"]) == {
        "source_kind",
        "source_commit",
        "source_path",
        "conversion",
        "license_code",
    }

    # No answer keys / hidden tests / internal review metadata anywhere in the DTO.
    def all_keys(node) -> set[str]:
        if isinstance(node, dict):
            found = set(node)
            for value in node.values():
                found |= all_keys(value)
            return found
        if isinstance(node, list):
            found: set[str] = set()
            for item in node:
                found |= all_keys(item)
            return found
        return set()

    keys = all_keys(payload)
    for forbidden_key in (
        "answer",
        "answers",
        "hidden_tests",
        "solution",
        "reference_solution",
        "original_sha256",
        "release_key",
        "review_comment",
        "source_manifest",
    ):
        assert forbidden_key not in keys

    withdrawn = await withdraw_revision(
        content_session,
        revision_id=revision.id,
        actor="合成测试发布者",
        comment="撤回测试",
    )
    assert withdrawn.publication_status == "WITHDRAWN"
    again = await client.get(f"/api/v1/chapters/{revision.chapter_id}")
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_content_access_is_rejected(client):
    for path in ("/api/v1/courses", f"/api/v1/chapters/{uuid.uuid4()}"):
        response = await client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    post = await client.post(
        "/api/v1/reading-events",
        json={
            "client_event_id": "aaaaaaaa-1",
            "chapter_id": str(uuid.uuid4()),
            "revision": 1,
            "event_kind": "ENTER",
        },
    )
    assert post.status_code in {401, 403}


@pytest.mark.asyncio
async def test_neighbours_only_include_visible_chapters(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _lower(test_settings, "content.lower.nav")
    await login(client, "content.lower.nav", "synthetic-pass-1")

    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    assert chapter is not None
    detail = await client.get(f"/api/v1/chapters/{chapter.chapter_id}")
    assert detail.status_code == 200
    navigation = detail.json()["navigation"]
    # ch02 is JUNIOR, so a PRIMARY_LOWER student must see no neighbour at all.
    assert navigation == {"prev": None, "next": None}


@pytest.mark.asyncio
async def test_course_id_must_match_visible_chapter(content_session, client, test_settings):
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    await _junior(test_settings, "content.junior.course")
    await login(client, "content.junior.course", "synthetic-pass-1")

    chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    assert chapter is not None
    detail = await client.get(f"/api/v1/chapters/{chapter.chapter_id}")
    course_id = detail.json()["course_id"]

    unknown = await client.get(f"/api/v1/courses/{uuid.uuid4()}")
    assert unknown.status_code == 404
    visible = await client.get(f"/api/v1/courses/{course_id}")
    assert visible.status_code == 200
    # Course rows exist only through visible chapters; an unpublished legacy
    # course id is not readable even if the id is known.
    legacy_chapter = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert legacy_chapter is not None
    from app.modules.content.models import Chapter

    course_id_legacy = await content_session.scalar(
        select(Chapter.course_id).where(Chapter.id == legacy_chapter.chapter_id)
    )
    denied = await client.get(f"/api/v1/courses/{course_id_legacy}")
    assert denied.status_code == 404
    assert denied.json()["error"]["message"] == "课程不可用"
