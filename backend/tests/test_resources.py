"""T20 acceptance: real resource entry, permission truth and safe delivery.

R1 metadata completeness · R2 upload limits and ownership · R3 real
docx/pptx/video delivery · R4 unpublished/withdrawn/cross-stage/old links ·
R5 source vs preview vs temporary ticket · R6 active content isolation ·
R7 server-filtered Tutor candidates · R8 readable failures (no fake "ready") ·
R9 T05 auth/CSRF and T06 release semantics preserved.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.storage import LocalFileStore, StorageError
from app.core.storage.keys import StorageKeyError, validate_storage_key
from app.core.storage.tickets import TicketError, verify_ticket
from app.main import create_app
from app.modules.content.importer import import_package
from app.modules.content.models import ContentProfile, ReviewStatus
from app.modules.content.package import load_package
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import publish_revision, record_review
from app.modules.identity.models import Stage, UserRole
from app.modules.resources.models import (
    Resource,
    ResourceChapterLink,
    ResourceVariant,
)
from app.modules.resources.service import (
    allowed_resource_ids_for_teaching,
    authorized_resource_ids_for_teaching,
)
from app.modules.teaching.context import build_session_context
from app.modules.teaching.models import LessonSession
from app.modules.teaching.service import create_session
from tests.content_helpers import LEGACY_PACKAGE, revision_by_slug
from tests.identity_helpers import (
    ORIGIN,
    auth_headers,
    create_synthetic_user,
    csrf,
    login,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures/t20"
DOCX = FIXTURE_DIR / "synthetic-lesson.docx"
PPTX = FIXTURE_DIR / "synthetic-slides.pptx"
MP4 = FIXTURE_DIR / "synthetic-clip.mp4"
HTML_DECOY = FIXTURE_DIR / "decoy.html"
SVG_DECOY = FIXTURE_DIR / "decoy.svg"
RENAMED = FIXTURE_DIR / "renamed.mp4"

UUID_RE = __import__("re").compile(r"^[0-9a-f-]{36}$")
ADMIN_USER = "t20.admin"
ADMIN_PASSWORD = "synthetic-Admin-T20-1234"
STUDENT_PASSWORD = "synthetic-Student-T20-1234"

JUNIOR_COURSE, JUNIOR_CHAPTER = "python-first-steps", "ch05"
SENIOR_COURSE, SENIOR_CHAPTER = "algorithm-everyday", "ch03"


@pytest_asyncio.fixture
async def rctx(test_settings: Settings, tmp_path: Path):
    """A real app whose resource store lives in a per-test temp directory."""

    settings = test_settings.model_copy(
        update={"resource_storage_root": str(tmp_path / "resource-store")}
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:15173") as client:
        yield SimpleNamespace(client=client, settings=settings, app=app)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def viewer_for(stage: Stage, grade: int | None, profile: ContentProfile) -> ViewerScope:
    return ViewerScope(stage=stage, grade=grade, profile=profile)


async def publish_legacy(session: AsyncSession, course: str, chapter: str):
    """A real, publishable (non-fixture) chapter revision from the legacy pack."""

    await import_package(session, load_package(LEGACY_PACKAGE), dry_run=False)
    revision = await revision_by_slug(session, course, chapter, 1)
    assert revision is not None
    await record_review(
        session,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="human-reviewer-t20",
    )
    await publish_revision(session, revision_id=revision.id, actor="human-reviewer-t20")
    await session.commit()
    return revision


async def as_admin(rctx, *, username: str = ADMIN_USER) -> str:
    client = rctx.client
    await create_synthetic_user(
        rctx.settings,
        username=username,
        password=ADMIN_PASSWORD,
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    token = await csrf(client)
    response = await login(client, username, ADMIN_PASSWORD, csrf_header=token)
    assert response.status_code == 200, response.text
    # T05 rotates the CSRF token on login: writes must use the new one.
    return response.json()["csrf_token"]


async def sign_in(rctx, username: str, password: str) -> str:
    """Log in again; T05 rotates the CSRF token on every login."""

    client = rctx.client
    token = await csrf(client)
    response = await login(client, username, password, csrf_header=token)
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


async def as_student(rctx, *, username: str, stage: str = "JUNIOR", grade: int | None = 8) -> str:
    client = rctx.client
    await create_synthetic_user(
        rctx.settings,
        username=username,
        password=STUDENT_PASSWORD,
        stage=stage,
        grade=grade,
    )
    token = await csrf(client)
    response = await login(client, username, STUDENT_PASSWORD, csrf_header=token)
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


async def register(
    rctx,
    token: str,
    *,
    slug: str,
    kind: str,
    revision_id: uuid.UUID | None = None,
    stage: str = "JUNIOR",
    fixture: bool = False,
):
    body = {
        "slug": slug,
        "title": f"合成资源 {slug}",
        "description": "T20 合成测试资源（未人工审校）",
        "kind": kind,
        "stage": stage,
        "grade_min": None,
        "grade_max": None,
        "source_kind": "SYNTHETIC_FIXTURE" if fixture else "NEW_SOURCE",
        "source_note": "SYNTHETIC T20 TEST FILE",
        "license_code": "SYNTHETIC-FIXTURE" if fixture else "PROJECT-ORIGINAL",
        "license_note": "合成测试，仅团队内部验证",
        "chapter_revision_ids": [str(revision_id)] if revision_id else [],
        "knowledge_point_slugs": [],
        "is_test_fixture": fixture,
    }
    return await rctx.client.post("/api/v1/admin/resources", json=body, headers=auth_headers(token))


async def upload(
    rctx,
    token: str,
    resource_id: str,
    path: Path,
    *,
    variant: str = "SOURCE",
    declared: str | None = None,
    filename: str | None = None,
):
    headers = auth_headers(token)
    headers["X-Filename"] = filename or path.name
    if declared is not None:
        headers["Content-Type"] = declared
    else:
        headers.pop("Content-Type", None)
    return await rctx.client.put(
        f"/api/v1/admin/resources/{resource_id}/content?variant={variant}",
        content=path.read_bytes(),
        headers=headers,
    )


async def publish(rctx, token: str, resource_id: str):
    return await rctx.client.patch(
        f"/api/v1/admin/resources/{resource_id}",
        json={"review_status": "HUMAN_APPROVED", "publication_status": "PUBLISHED"},
        headers=auth_headers(token),
    )


async def make_published(rctx, token: str, *, slug: str, kind: str, revision_id, path: Path):
    created = await register(rctx, token, slug=slug, kind=kind, revision_id=revision_id)
    assert created.status_code == 201, created.text
    resource_id = created.json()["id"]
    stored = await upload(rctx, token, resource_id, path, declared="application/octet-stream")
    assert stored.status_code == 200, stored.text
    published = await publish(rctx, token, resource_id)
    assert published.status_code == 200, published.text
    return resource_id


# --------------------------------------------------------------------------- admin catalogue
@pytest.mark.asyncio
async def test_learning_catalogue_tracks_actual_resource_bytes(rctx, content_session) -> None:
    token = await as_admin(rctx)
    resource_id = await make_published(
        rctx, token, slug="catalogue-file-check", kind="WORD", revision_id=None, path=DOCX
    )
    await as_student(rctx, username="catalogue.file.student")
    url = "/api/v1/learning/catalog?kind=RESOURCE&q=catalogue-file-check"
    available = await rctx.client.get(url)
    assert available.status_code == 200, available.text
    assert available.json()["items"][0]["available"] is True
    saved = await rctx.client.put(
        f"/api/v1/learning/bookshelf/RESOURCE/{resource_id}",
        headers=auth_headers(await csrf(rctx.client)),
    )
    assert saved.status_code == 201, saved.text
    shelf = await rctx.client.get("/api/v1/learning/bookshelf")
    assert shelf.status_code == 200, shelf.text
    assert shelf.json()["items"][0]["available"] is True
    variant = await content_session.scalar(
        select(ResourceVariant).where(ResourceVariant.resource_id == uuid.UUID(resource_id))
    )
    assert variant is not None
    (Path(rctx.settings.resource_storage_root) / variant.storage_key).unlink()
    missing = await rctx.client.get(url)
    assert missing.status_code == 200, missing.text
    item = missing.json()["items"][0]
    assert item["available"] is False
    assert item["unavailable_reason"] == "RESOURCE_FILE_MISSING"
    shelf = await rctx.client.get("/api/v1/learning/bookshelf")
    assert shelf.status_code == 200, shelf.text
    assert shelf.json()["items"][0]["available"] is False
    token = await sign_in(rctx, ADMIN_USER, ADMIN_PASSWORD)
    republished = await publish(rctx, token, resource_id)
    assert republished.status_code == 409, republished.text


@pytest.mark.asyncio
async def test_admin_resource_list_filters_and_paginates_without_storage_keys(rctx) -> None:
    assert (await rctx.client.get("/api/v1/admin/resources")).status_code == 401
    token = await as_admin(rctx)
    first = await register(rctx, token, slug="catalog-alpha", kind="WORD", stage="JUNIOR")
    second = await register(rctx, token, slug="catalog-beta", kind="PDF", stage="SENIOR")
    assert first.status_code == second.status_code == 201
    changed = await rctx.client.patch(
        f"/api/v1/admin/resources/{second.json()['id']}",
        json={"review_status": "HUMAN_APPROVED"},
        headers=auth_headers(token),
    )
    assert changed.status_code == 200, changed.text

    all_rows = await rctx.client.get("/api/v1/admin/resources")
    assert all_rows.status_code == 200
    assert all_rows.json()["total"] == 2
    assert [item["slug"] for item in all_rows.json()["items"]] == ["catalog-alpha", "catalog-beta"]
    assert "storage_key" not in all_rows.text
    first_page = await rctx.client.get("/api/v1/admin/resources?limit=1&offset=1")
    assert first_page.json()["total"] == 2
    assert first_page.json()["items"][0]["slug"] == "catalog-beta"
    for query, expected in (
        ("q=alpha", "catalog-alpha"),
        ("kind=PDF", "catalog-beta"),
        ("stage=JUNIOR", "catalog-alpha"),
        ("status=UNREVIEWED", "catalog-alpha"),
        ("status=HUMAN_APPROVED", "catalog-beta"),
    ):
        response = await rctx.client.get(f"/api/v1/admin/resources?{query}")
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["slug"] == expected
    assert (await rctx.client.get("/api/v1/admin/resources?limit=0")).status_code == 422
    assert (await rctx.client.get("/api/v1/admin/resources?status=INVALID")).status_code == 422


# --------------------------------------------------------------------------- R1
@pytest.mark.asyncio
async def test_r1_metadata_links_are_complete_and_keys_stay_internal(rctx, content_session) -> None:
    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    token = await as_admin(rctx)

    created = await register(rctx, token, slug="t20-r1-docx", kind="WORD", revision_id=revision.id)
    assert created.status_code == 201, created.text
    body = created.json()
    assert "storage_key" not in created.text
    assert body["chapter_revision_ids"] == [str(revision.id)]
    assert body["knowledge_point_slugs"] == []
    assert body["stage"] == "JUNIOR"
    assert body["review_status"] == "UNREVIEWED" and body["publication_status"] == "DRAFT"
    assert body["is_test_fixture"] is False and body["content_notice"] is None

    stored = await upload(rctx, token, body["id"], DOCX, declared="application/octet-stream")
    assert stored.status_code == 200, stored.text
    assert stored.json()["sha256"] == sha256_of(DOCX)

    row = await content_session.scalar(select(Resource).where(Resource.id == uuid.UUID(body["id"])))
    assert row is not None and row.license_code == "PROJECT-ORIGINAL"
    link = await content_session.scalar(
        select(ResourceChapterLink).where(ResourceChapterLink.resource_id == row.id)
    )
    assert link is not None and link.chapter_revision_id == revision.id
    variant = await content_session.scalar(
        select(ResourceVariant).where(ResourceVariant.resource_id == row.id)
    )
    assert variant is not None and variant.variant == "SOURCE"
    assert variant.detected_mime.endswith("wordprocessingml.document")
    assert variant.storage_key.startswith(f"resources/{row.id}/")
    store = LocalFileStore(Path(rctx.settings.resource_storage_root))
    assert store.size(variant.storage_key) == DOCX.stat().st_size

    # a synthetic fixture resource can be registered but never published
    fixture_row = await register(
        rctx, token, slug="t20-r1-fixture", kind="WORD", revision_id=revision.id, fixture=True
    )
    assert fixture_row.status_code == 201, fixture_row.text
    fixture_id = fixture_row.json()["id"]
    await upload(rctx, token, fixture_id, DOCX, declared="application/octet-stream")
    refused = await publish(rctx, token, fixture_id)
    assert refused.status_code == 409, refused.text
    assert "RESOURCE_FIXTURE_NOT_PUBLISHABLE" in refused.text


# --------------------------------------------------------------------------- R2
@pytest.mark.asyncio
async def test_r2_upload_limits_and_ownership(rctx, content_session) -> None:
    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    token = await as_admin(rctx)
    created = await register(
        rctx, token, slug="t20-r2-video", kind="VIDEO", revision_id=revision.id
    )
    resource_id = created.json()["id"]

    # HTML bytes wearing an .mp4 name
    renamed = await upload(rctx, token, resource_id, RENAMED, declared="video/mp4")
    assert renamed.status_code == 415, renamed.text
    assert "RESOURCE_ACTIVE_CONTENT_REJECTED" in renamed.text

    # declared SVG is active content
    svg = await upload(rctx, token, resource_id, SVG_DECOY, declared="image/svg+xml")
    assert svg.status_code == 415 and "RESOURCE_ACTIVE_CONTENT_REJECTED" in svg.text

    # real docx bytes declared as video => declared/real MIME mismatch
    mismatch = await upload(rctx, token, resource_id, DOCX, declared="video/mp4")
    assert mismatch.status_code == 415, mismatch.text
    assert "RESOURCE_MIME_MISMATCH" in mismatch.text

    # real docx bytes renamed to .mp4 => extension/real type mismatch
    renamed_ext = await upload(
        rctx,
        token,
        resource_id,
        DOCX,
        declared="application/octet-stream",
        filename="lesson.mp4",
    )
    assert renamed_ext.status_code == 415, renamed_ext.text
    assert "RESOURCE_EXTENSION_MISMATCH" in renamed_ext.text

    # a Word file cannot be registered as a VIDEO resource
    other = await register(rctx, token, slug="t20-r2-kind", kind="VIDEO", revision_id=revision.id)
    wrong_kind = await upload(
        rctx,
        token,
        other.json()["id"],
        DOCX,
        declared="application/octet-stream",
        filename="lesson.docx",
    )
    assert wrong_kind.status_code == 415 and "RESOURCE_KIND_MISMATCH" in wrong_kind.text

    # declared types that do not contradict the real bytes are accepted:
    # a desktop OS alias (Chrome + WPS reports application/wps-office.docx for
    # a real .docx) and an explicitly opaque body both pass; the bytes decide.
    word = await register(rctx, token, slug="t20-r2-word", kind="WORD", revision_id=revision.id)
    word_id = word.json()["id"]
    canonical = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    for index, declared in enumerate(
        (canonical, "application/wps-office.docx", "application/octet-stream")
    ):
        accepted = await upload(
            rctx,
            token,
            word_id,
            DOCX,
            declared=declared,
            filename=f"lesson-{index}.docx",
        )
        assert accepted.status_code == 200, (declared, accepted.text)

    # size cap is enforced while streaming, before publication
    original = rctx.app.state.settings
    rctx.app.state.settings = original.model_copy(update={"resource_upload_max_bytes": 512})
    try:
        too_big = await upload(rctx, token, resource_id, MP4, declared="video/mp4")
        assert too_big.status_code == 413, too_big.text
        assert "STORAGE_TOO_LARGE" in too_big.text
    finally:
        rctx.app.state.settings = original

    # ownership: a student can neither register nor upload
    student_token = await as_student(rctx, username="t20.r2.student")
    assert (
        await register(
            rctx, student_token, slug="t20-r2-student", kind="WORD", revision_id=revision.id
        )
    ).status_code == 403
    assert (await upload(rctx, student_token, resource_id, DOCX)).status_code == 403

    # path traversal and symlinks are refused at the storage boundary
    for key in ["../escape.docx", "/etc/passwd", "resources/../../x.docx", "a\\b.docx"]:
        with pytest.raises(StorageKeyError):
            validate_storage_key(key)

    root = Path(rctx.settings.resource_storage_root)
    outside = root.parent / "outside-target"
    outside.mkdir(parents=True, exist_ok=True)
    link = root / "linked-dir"
    if not link.exists():
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageError):
        LocalFileStore(root).resolve("linked-dir/payload.docx")


# --------------------------------------------------------------------------- R3
@pytest.mark.asyncio
async def test_r3_real_docx_pptx_video_download_and_video_range(rctx, content_session) -> None:
    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    token = await as_admin(rctx)
    resources = {}
    for slug, kind, path in (
        ("t20-r3-doc", "WORD", DOCX),
        ("t20-r3-ppt", "SLIDES", PPTX),
        ("t20-r3-video", "VIDEO", MP4),
    ):
        resources[kind] = (
            await make_published(
                rctx, token, slug=slug, kind=kind, revision_id=revision.id, path=path
            ),
            path,
        )

    await as_student(rctx, username="t20.r3.student")
    for kind, (resource_id, path) in resources.items():
        response = await rctx.client.get(f"/api/v1/resources/{resource_id}/content")
        assert response.status_code == 200, response.text
        assert response.content == path.read_bytes(), kind
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        # T05 middleware already forces no-store; my header must not weaken it.
        assert "no-store" in response.headers["Cache-Control"]
        assert "sandbox" in response.headers["Content-Security-Policy"]
        assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
        if kind == "VIDEO":
            assert response.headers["Content-Disposition"].startswith("inline")
            assert response.headers["Content-Type"] == "video/mp4"
        else:
            assert response.headers["Content-Disposition"].startswith("attachment")

    # real partial bytes (a <video> element needs range requests)
    video_id = resources["VIDEO"][0]
    ranged = await rctx.client.get(
        f"/api/v1/resources/{video_id}/content", headers={"Range": "bytes=0-99"}
    )
    assert ranged.status_code in (200, 206), ranged.text
    assert ranged.content == MP4.read_bytes()[:100]
    assert len(ranged.content) == 100


# --------------------------------------------------------------------------- R4
@pytest.mark.asyncio
async def test_r4_unpublished_withdrawn_cross_stage_and_old_links(rctx, content_session) -> None:
    junior_revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    senior_revision = await publish_legacy(content_session, SENIOR_COURSE, SENIOR_CHAPTER)
    token = await as_admin(rctx)

    draft = await register(
        rctx, token, slug="t20-r4-draft", kind="WORD", revision_id=junior_revision.id
    )
    draft_id = draft.json()["id"]
    await upload(rctx, token, draft_id, DOCX, declared="application/octet-stream")

    # binding a SENIOR resource to a JUNIOR revision is refused
    cross = await register(
        rctx,
        token,
        slug="t20-r4-cross",
        kind="WORD",
        stage="SENIOR",
        revision_id=junior_revision.id,
    )
    assert cross.status_code == 409 and "RESOURCE_REVISION_STAGE" in cross.text

    published_id = await make_published(
        rctx,
        token,
        slug="t20-r4-published",
        kind="SLIDES",
        revision_id=junior_revision.id,
        path=PPTX,
    )
    assert senior_revision is not None

    junior_token = await as_student(rctx, username="t20.r4.junior")
    listing = await rctx.client.get("/api/v1/resources")
    assert listing.status_code == 200
    ids = [item["id"] for item in listing.json()["items"]]
    assert published_id in ids and draft_id not in ids

    ticket = await rctx.client.post(
        f"/api/v1/resources/{published_id}/tickets", headers=auth_headers(junior_token)
    )
    assert ticket.status_code == 200, ticket.text
    link = ticket.json()["url"]
    assert (await rctx.client.get(link)).status_code == 200

    # a SENIOR student cannot open a JUNIOR resource even with the exact id
    senior_token = await as_student(rctx, username="t20.r4.senior", stage="SENIOR", grade=11)
    assert senior_token
    assert (await rctx.client.get(f"/api/v1/resources/{published_id}")).status_code == 404
    assert (await rctx.client.get(f"/api/v1/resources/{published_id}/content")).status_code == 404

    # switch back to the admin session (T05 keeps one session per client)
    admin_token = await sign_in(rctx, ADMIN_USER, ADMIN_PASSWORD)
    withdrawn = await rctx.client.patch(
        f"/api/v1/admin/resources/{published_id}",
        json={"publication_status": "WITHDRAWN"},
        headers=auth_headers(admin_token),
    )
    assert withdrawn.status_code == 200, withdrawn.text

    await sign_in(rctx, "t20.r4.junior", STUDENT_PASSWORD)
    assert (await rctx.client.get(f"/api/v1/resources/{published_id}/content")).status_code == 404
    assert (await rctx.client.get(link)).status_code == 404
    after = await rctx.client.get("/api/v1/resources")
    assert published_id not in [item["id"] for item in after.json()["items"]]


# --------------------------------------------------------------------------- R5
@pytest.mark.asyncio
async def test_r5_source_preview_and_ticket_are_distinct(rctx, content_session) -> None:
    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    token = await as_admin(rctx)
    created = await register(rctx, token, slug="t20-r5", kind="SLIDES", revision_id=revision.id)
    resource_id = created.json()["id"]
    assert (
        await upload(rctx, token, resource_id, PPTX, declared="application/octet-stream")
    ).status_code == 200
    preview = await upload(
        rctx, token, resource_id, PPTX, variant="PREVIEW", declared="application/octet-stream"
    )
    assert preview.status_code == 200, preview.text
    assert (await publish(rctx, token, resource_id)).status_code == 200

    rows = list(
        await content_session.scalars(
            select(ResourceVariant).where(ResourceVariant.resource_id == uuid.UUID(resource_id))
        )
    )
    assert {row.variant for row in rows} == {"SOURCE", "PREVIEW"}
    assert len({row.storage_key for row in rows}) == 2

    student_token = await as_student(rctx, username="t20.r5.owner")
    detail = await rctx.client.get(f"/api/v1/resources/{resource_id}")
    assert {item["variant"] for item in detail.json()["variants"]} == {"SOURCE", "PREVIEW"}
    assert all(item["available"] for item in detail.json()["variants"])

    ticket = await rctx.client.post(
        f"/api/v1/resources/{resource_id}/tickets", headers=auth_headers(student_token)
    )
    assert ticket.status_code == 200
    link = ticket.json()["url"]
    assert link.startswith("/api/v1/resources/content/")
    token_part = link.rsplit("/", 1)[-1]

    # the temporary link is never stored as a resource/file identifier
    for model, column in (
        (Resource, Resource.stable_slug),
        (ResourceVariant, ResourceVariant.storage_key),
        (ResourceVariant, ResourceVariant.original_filename),
    ):
        hit = await content_session.scalar(
            select(func.count()).select_from(model).where(column == token_part)
        )
        assert hit == 0

    # a leaked link belongs to its owner only, and expires on its own
    await as_student(rctx, username="t20.r5.other")
    leaked = await rctx.client.get(link)
    assert leaked.status_code == 403, leaked.text
    assert "RESOURCE_TICKET_OWNER" in leaked.text

    with pytest.raises(TicketError) as expired:
        verify_ticket(rctx.settings.app_session_secret or "", token_part, now=4102444800)
    assert expired.value.code == "RESOURCE_TICKET_EXPIRED"


# --------------------------------------------------------------------------- R6
@pytest.mark.asyncio
async def test_r6_active_content_never_executes_same_origin(rctx, content_session) -> None:
    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    token = await as_admin(rctx)
    resource_id = await make_published(
        rctx, token, slug="t20-r6", kind="WORD", revision_id=revision.id, path=DOCX
    )

    # even if an HTML payload reached the store, delivery forces a download
    store = LocalFileStore(Path(rctx.settings.resource_storage_root))
    forced = store.resolve(f"resources/{resource_id}/source-forced.html")
    forced.parent.mkdir(parents=True, exist_ok=True)
    forced.write_bytes(HTML_DECOY.read_bytes())
    variant = await content_session.scalar(
        select(ResourceVariant).where(ResourceVariant.resource_id == uuid.UUID(resource_id))
    )
    variant.storage_key = f"resources/{resource_id}/source-forced.html"
    variant.detected_mime = "text/html"
    await content_session.commit()

    await as_student(rctx, username="t20.r6.viewer")
    response = await rctx.client.get(f"/api/v1/resources/{resource_id}/content")
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response.headers["Content-Security-Policy"]

    # and the upload path refuses active content outright (admin session again)
    admin_token = await sign_in(rctx, ADMIN_USER, ADMIN_PASSWORD)
    svg = await upload(rctx, admin_token, resource_id, SVG_DECOY, declared="image/svg+xml")
    assert svg.status_code == 415 and "RESOURCE_ACTIVE_CONTENT_REJECTED" in svg.text


# --------------------------------------------------------------------------- R7
@pytest.mark.asyncio
async def test_r7_tutor_candidates_are_server_filtered(rctx, content_session) -> None:
    junior_revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    senior_revision = await publish_legacy(content_session, SENIOR_COURSE, SENIOR_CHAPTER)
    admin = await create_synthetic_user(
        rctx.settings,
        username="t20.r7.admin",
        password=ADMIN_PASSWORD,
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )

    async def add(slug: str, *, stage: str, revision_id, review: str, publication: str):
        row = Resource(
            stable_slug=slug,
            title=slug,
            description="",
            kind="WORD",
            stage=stage,
            grade_min=None,
            grade_max=None,
            source_kind="NEW_SOURCE",
            source_note="",
            license_code="PROJECT-ORIGINAL",
            license_note="",
            review_status=review,
            publication_status=publication,
            # the DB trigger requires a real reviewer identity for approval
            reviewer_id=admin.id if review == "HUMAN_APPROVED" else None,
            reviewed_at=datetime.now(UTC) if review == "HUMAN_APPROVED" else None,
            is_test_fixture=False,
            uploaded_by_user_id=admin.id,
        )
        content_session.add(row)
        await content_session.flush()
        content_session.add(
            ResourceChapterLink(resource_id=row.id, chapter_revision_id=revision_id)
        )
        content_session.add(
            ResourceVariant(
                resource_id=row.id,
                variant="SOURCE",
                storage_key=f"resources/{row.id}/source-{slug}.docx",
                original_filename="lesson.docx",
                declared_mime="",
                detected_mime="application/octet-stream",
                size_bytes=10,
                sha256="0" * 64,
            )
        )
        await content_session.commit()
        return row

    good = await add(
        "t20-r7-good",
        stage="JUNIOR",
        revision_id=junior_revision.id,
        review="HUMAN_APPROVED",
        publication="PUBLISHED",
    )
    draft = await add(
        "t20-r7-draft",
        stage="JUNIOR",
        revision_id=junior_revision.id,
        review="UNREVIEWED",
        publication="DRAFT",
    )
    withdrawn = await add(
        "t20-r7-withdrawn",
        stage="JUNIOR",
        revision_id=junior_revision.id,
        review="HUMAN_APPROVED",
        publication="WITHDRAWN",
    )
    senior = await add(
        "t20-r7-senior",
        stage="SENIOR",
        revision_id=senior_revision.id,
        review="HUMAN_APPROVED",
        publication="PUBLISHED",
    )

    viewer = viewer_for(Stage.JUNIOR, 8, ContentProfile.DEVELOPMENT)
    authorized = await authorized_resource_ids_for_teaching(
        content_session, viewer=viewer, revision_id=junior_revision.id
    )
    assert str(good.id) in authorized
    for excluded in (draft, withdrawn, senior):
        assert str(excluded.id) not in authorized

    # a published resource bound to a different revision is not authorized here
    other_revision = await add(
        "t20-r7-other-revision",
        stage="JUNIOR",
        revision_id=senior_revision.id,
        review="HUMAN_APPROVED",
        publication="PUBLISHED",
    )
    authorized_junior = await authorized_resource_ids_for_teaching(
        content_session, viewer=viewer, revision_id=junior_revision.id
    )
    assert str(other_revision.id) not in authorized_junior

    # the gate is fail-closed and shape-checked
    assert allowed_resource_ids_for_teaching(authorized_ids=None) == []
    assert allowed_resource_ids_for_teaching(
        authorized_ids=[str(good.id), "https://evil.example/payload", "", "../../etc"]
    ) == [str(good.id)]

    # the teaching context receives only the authorized set
    with_ids = build_session_context(
        chapter_slug=JUNIOR_CHAPTER,
        chapter_id=str(junior_revision.chapter_id),
        chapter_title="Python 起步",
        revision_number=junior_revision.revision,
        revision_id=str(junior_revision.id),
        stage="JUNIOR",
        objectives=["objective"],
        blocks=[],
        authorized_resource_ids=[str(good.id)],
    )
    assert with_ids["allowed_resource_ids"] == [str(good.id)]
    without = build_session_context(
        chapter_slug=JUNIOR_CHAPTER,
        chapter_id=str(junior_revision.chapter_id),
        chapter_title="Python 起步",
        revision_number=junior_revision.revision,
        revision_id=str(junior_revision.id),
        stage="JUNIOR",
        objectives=["objective"],
        blocks=[],
    )
    assert without["allowed_resource_ids"] == []


# --------------------------------------------------------------------------- R8
@pytest.mark.asyncio
async def test_r8_missing_file_is_reported_not_blank(rctx, content_session) -> None:
    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    token = await as_admin(rctx)
    resource_id = await make_published(
        rctx, token, slug="t20-r8", kind="WORD", revision_id=revision.id, path=DOCX
    )
    variant = await content_session.scalar(
        select(ResourceVariant).where(ResourceVariant.resource_id == uuid.UUID(resource_id))
    )
    LocalFileStore(Path(rctx.settings.resource_storage_root)).resolve(variant.storage_key).unlink()

    await as_student(rctx, username="t20.r8.viewer")
    detail = await rctx.client.get(f"/api/v1/resources/{resource_id}")
    assert detail.status_code == 200, detail.text
    item = detail.json()["variants"][0]
    assert item["available"] is False
    assert item["unavailable_reason"] == "RESOURCE_FILE_MISSING"

    content = await rctx.client.get(f"/api/v1/resources/{resource_id}/content")
    assert content.status_code == 404
    assert "RESOURCE_FILE_MISSING" in content.text

    # a resource with no registered file at all is never advertised as ready
    admin_token = await sign_in(rctx, ADMIN_USER, ADMIN_PASSWORD)
    empty = await register(
        rctx, admin_token, slug="t20-r8-empty", kind="WORD", revision_id=revision.id
    )
    empty_id = empty.json()["id"]
    await sign_in(rctx, "t20.r8.viewer", STUDENT_PASSWORD)
    # a draft with no bytes is simply not visible: no blank "ready" card exists
    empty_detail = await rctx.client.get(f"/api/v1/resources/{empty_id}")
    assert empty_detail.status_code == 404
    assert "RESOURCE_NOT_VISIBLE" in empty_detail.text

    # publishing without a real file is refused
    admin_token = await sign_in(rctx, ADMIN_USER, ADMIN_PASSWORD)
    blocked = await publish(rctx, admin_token, empty_id)
    assert blocked.status_code == 409 and "RESOURCE_FILE_MISSING" in blocked.text


# --------------------------------------------------------------------------- R9
@pytest.mark.asyncio
async def test_r9_auth_csrf_and_release_semantics_preserved(rctx, content_session) -> None:
    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)

    assert (await rctx.client.get("/api/v1/resources")).status_code == 401

    token = await as_admin(rctx)
    payload = {
        "slug": "t20-r9-csrf",
        "title": "x",
        "description": "",
        "kind": "WORD",
        "stage": "JUNIOR",
        "source_kind": "NEW_SOURCE",
        "license_code": "PROJECT-ORIGINAL",
        "chapter_revision_ids": [str(revision.id)],
        "knowledge_point_slugs": [],
        "is_test_fixture": False,
        "grade_min": None,
        "grade_max": None,
        "source_note": "",
        "license_note": "",
    }
    no_token = await rctx.client.post(
        "/api/v1/admin/resources", json=payload, headers={"Origin": ORIGIN}
    )
    assert no_token.status_code == 403
    bad_origin = await rctx.client.post(
        "/api/v1/admin/resources",
        json=payload,
        headers={"Origin": "https://evil.example", "X-CSRF-Token": token},
    )
    assert bad_origin.status_code == 403

    await as_student(rctx, username="t20.r9.student")
    assert (await rctx.client.get("/api/v1/admin/resources")).status_code == 403

    # T06 release semantics are untouched for a published chapter
    detail = await rctx.client.get(f"/api/v1/chapters/{revision.chapter_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["revision"] == revision.revision
    assert detail.json()["publication_status"] == "PUBLISHED"
    assert "storage_key" not in detail.text


# --------------------------------------------------------------------------- R7 (production path)
async def _insert_resource(
    db: AsyncSession,
    *,
    slug: str,
    stage: str,
    revision_id,
    review: str,
    publication: str,
    uploader_id,
    with_variant: bool = True,
):
    """Register a resource row directly so each filter branch can be isolated."""

    row = Resource(
        stable_slug=slug,
        title=slug,
        description="",
        kind="WORD",
        stage=stage,
        grade_min=None,
        grade_max=None,
        source_kind="NEW_SOURCE",
        source_note="",
        license_code="PROJECT-ORIGINAL",
        license_note="",
        review_status=review,
        publication_status=publication,
        reviewer_id=uploader_id if review == "HUMAN_APPROVED" else None,
        reviewed_at=datetime.now(UTC) if review == "HUMAN_APPROVED" else None,
        is_test_fixture=False,
        uploaded_by_user_id=uploader_id,
    )
    db.add(row)
    await db.flush()
    db.add(ResourceChapterLink(resource_id=row.id, chapter_revision_id=revision_id))
    if with_variant:
        db.add(
            ResourceVariant(
                resource_id=row.id,
                variant="SOURCE",
                storage_key=f"resources/{row.id}/source-{slug}.docx",
                original_filename="lesson.docx",
                declared_mime="",
                detected_mime="application/octet-stream",
                size_bytes=10,
                sha256="0" * 64,
            )
        )
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_r7_production_session_receives_only_authorized_resources(
    rctx, content_session
) -> None:
    """The real `create_session` call site injects the server-filtered set."""

    junior_revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    senior_revision = await publish_legacy(content_session, SENIOR_COURSE, SENIOR_CHAPTER)
    uploader = await create_synthetic_user(
        rctx.settings,
        username="t20.r7b.uploader",
        password=ADMIN_PASSWORD,
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    student = await create_synthetic_user(
        rctx.settings,
        username="t20.r7b.student",
        password=STUDENT_PASSWORD,
        stage="JUNIOR",
        grade=8,
    )

    good = await _insert_resource(
        content_session,
        slug="t20-r7b-good",
        stage="JUNIOR",
        revision_id=junior_revision.id,
        review="HUMAN_APPROVED",
        publication="PUBLISHED",
        uploader_id=uploader.id,
    )
    draft = await _insert_resource(
        content_session,
        slug="t20-r7b-draft",
        stage="JUNIOR",
        revision_id=junior_revision.id,
        review="UNREVIEWED",
        publication="DRAFT",
        uploader_id=uploader.id,
    )
    withdrawn = await _insert_resource(
        content_session,
        slug="t20-r7b-withdrawn",
        stage="JUNIOR",
        revision_id=junior_revision.id,
        review="HUMAN_APPROVED",
        publication="WITHDRAWN",
        uploader_id=uploader.id,
    )
    senior = await _insert_resource(
        content_session,
        slug="t20-r7b-senior",
        stage="SENIOR",
        revision_id=senior_revision.id,
        review="HUMAN_APPROVED",
        publication="PUBLISHED",
        uploader_id=uploader.id,
    )
    other_revision = await _insert_resource(
        content_session,
        slug="t20-r7b-other-rev",
        stage="JUNIOR",
        revision_id=senior_revision.id,
        review="HUMAN_APPROVED",
        publication="PUBLISHED",
        uploader_id=uploader.id,
    )
    no_bytes = await _insert_resource(
        content_session,
        slug="t20-r7b-no-bytes",
        stage="JUNIOR",
        revision_id=junior_revision.id,
        review="HUMAN_APPROVED",
        publication="PUBLISHED",
        uploader_id=uploader.id,
        with_variant=False,
    )

    session = await create_session(
        content_session,
        settings=rctx.settings,
        user=student,
        chapter_id=junior_revision.chapter_id,
    )
    allowed = session.context["allowed_resource_ids"]

    assert str(good.id) in allowed
    for excluded in (draft, withdrawn, senior, other_revision, no_bytes):
        assert str(excluded.id) not in allowed
    # every entry is a real registry id, not a title, path or ticket
    for value in allowed:
        assert UUID_RE.match(value)


@pytest.mark.asyncio
async def test_r7_lookup_failure_is_fail_closed(rctx, content_session, monkeypatch) -> None:
    """If the authorization lookup fails, no session is created at all."""

    revision = await publish_legacy(content_session, JUNIOR_COURSE, JUNIOR_CHAPTER)
    student = await create_synthetic_user(
        rctx.settings,
        username="t20.r7c.student",
        password=STUDENT_PASSWORD,
        stage="JUNIOR",
        grade=8,
    )

    async def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic lookup failure")

    monkeypatch.setattr("app.modules.teaching.service.authorized_resource_ids_for_teaching", boom)
    with pytest.raises(RuntimeError):
        await create_session(
            content_session,
            settings=rctx.settings,
            user=student,
            chapter_id=revision.chapter_id,
        )
    sessions = await content_session.scalar(select(func.count()).select_from(LessonSession))
    assert sessions == 0
