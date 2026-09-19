from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.modules.content.importer import (
    ContentNotPublishable,
    RevisionHashMismatch,
    import_package,
)
from app.modules.content.models import PublicationStatus, ReviewStatus
from app.modules.content.package import PackageValidationError, load_package
from app.modules.content.service import (
    ContentReviewError,
    publish_revision,
    record_review,
)
from tests.content_helpers import (
    FIXTURE_PACKAGE,
    LEGACY_PACKAGE,
    chapter_file,
    copy_fixture_package,
    course_file,
    edit_json,
    revision_by_slug,
    rewrite_chapter,
    table_counts,
)


def _reuse_counters(expected_chapters: int = 2) -> dict[str, int]:
    return {
        "courses_created": 0,
        "courses_reused": 1,
        "chapters_created": 0,
        "chapters_reused": expected_chapters,
        "revisions_created": 0,
        "revisions_reused": expected_chapters,
        "knowledge_points_created": 0,
        "knowledge_points_reused": 1,
        "knowledge_point_links_created": 0,
    }


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_then_import_is_idempotent(
    content_session, tmp_path: Path
) -> None:
    package = load_package(FIXTURE_PACKAGE)
    mirror = tmp_path / "mirror"
    before = await table_counts(content_session)

    dry = await import_package(content_session, package, dry_run=True, mirror_root=mirror)
    assert dry.dry_run is True
    assert dry.counters["revisions_created"] == 2
    assert await table_counts(content_session) == before
    assert not mirror.exists()

    first = await import_package(content_session, package, dry_run=False, mirror_root=mirror)
    assert first.counters["revisions_created"] == 2
    assert first.counters["knowledge_points_created"] == 1
    assert first.counters["knowledge_point_links_created"] == 2
    assert first.mirror_pending is False
    after_first = await table_counts(content_session)
    assert after_first["content_courses"] == 1
    assert after_first["content_chapters"] == 2
    assert after_first["content_chapter_revisions"] == 2
    assert after_first["content_knowledge_points"] == 1
    assert after_first["content_revision_knowledge_points"] == 2
    assert after_first["content_releases"] == 1
    assert after_first["content_chapter_review_states"] == 2
    assert sorted(p.name for p in mirror.rglob("*.json")) == ["ch01-r1.json", "ch02-r1.json"]

    second = await import_package(content_session, package, dry_run=False, mirror_root=mirror)
    assert second.counters == _reuse_counters()
    assert second.mirrored == ["ch01:REUSE", "ch02:REUSE"]
    assert await table_counts(content_session) == after_first


@pytest.mark.asyncio
async def test_same_revision_with_different_hash_is_rejected(
    content_session, tmp_path: Path
) -> None:
    package = load_package(FIXTURE_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    before = await table_counts(content_session)

    mutated = copy_fixture_package(tmp_path)
    edit_json(
        mutated / "release.json",
        lambda data: data.__setitem__("release_key", "synthetic-t06-fixtures-v1-alt"),
    )
    document = json.loads(chapter_file(mutated, "ch01").read_text(encoding="utf-8"))
    blocks = [
        {**document["blocks"][0], "text": "合成样例：被改动的标题"},
        *document["blocks"][1:],
    ]
    rewrite_chapter(mutated, "ch01", blocks)
    changed = load_package(mutated)

    with pytest.raises(RevisionHashMismatch):
        await import_package(content_session, changed, dry_run=False)
    await content_session.rollback()
    assert await table_counts(content_session) == before


@pytest.mark.asyncio
async def test_new_revision_is_added_and_old_revision_stays_immutable(
    content_session, tmp_path: Path
) -> None:
    package = load_package(FIXTURE_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    original = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    assert original is not None
    revision_id = original.id
    original_hash = original.content_hash
    original_body = json.dumps(original.body, ensure_ascii=False, sort_keys=True)
    links_before = (
        await content_session.execute(
            text("SELECT count(*) FROM content_revision_knowledge_points WHERE revision_id = :rid"),
            {"rid": revision_id},
        )
    ).scalar_one()

    revised = copy_fixture_package(tmp_path)
    edit_json(
        revised / "release.json",
        lambda data: data.__setitem__("release_key", "synthetic-t06-fixtures-v2"),
    )
    edit_json(
        course_file(revised),
        lambda data: data["chapters"][0].__setitem__("revision", 2),
    )
    document = json.loads(chapter_file(revised, "ch01").read_text(encoding="utf-8"))
    document["revision"] = 2
    blocks = [
        {**document["blocks"][0], "text": "合成样例：第二版标题"},
        *document["blocks"][1:],
    ]
    document["blocks"] = blocks
    chapter_path = chapter_file(revised, "ch01")
    chapter_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    result = await import_package(content_session, load_package(revised), dry_run=False)
    assert result.counters["revisions_created"] == 1
    assert result.counters["revisions_reused"] == 1

    content_session.expire_all()
    reloaded = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    assert reloaded is not None
    assert reloaded.content_hash == original_hash
    assert json.dumps(reloaded.body, ensure_ascii=False, sort_keys=True) == original_body
    links_after = (
        await content_session.execute(
            text("SELECT count(*) FROM content_revision_knowledge_points WHERE revision_id = :rid"),
            {"rid": revision_id},
        )
    ).scalar_one()
    assert links_after == links_before

    with pytest.raises(Exception) as update_error:
        await content_session.execute(
            text("UPDATE content_chapter_revisions SET revision = 99 WHERE id = :rid"),
            {"rid": revision_id},
        )
    assert "immutable" in str(update_error.value)
    await content_session.rollback()

    with pytest.raises(Exception) as delete_error:
        await content_session.execute(
            text("DELETE FROM content_chapter_revisions WHERE id = :rid"), {"rid": revision_id}
        )
    assert "immutable" in str(delete_error.value)
    await content_session.rollback()


@pytest.mark.asyncio
async def test_invalid_package_leaves_no_partial_rows(content_session, tmp_path: Path) -> None:
    before = await table_counts(content_session)
    package_dir = copy_fixture_package(tmp_path)
    edit_json(
        course_file(package_dir),
        lambda data: data["chapters"][1].__setitem__("license_code", "UNKNOWN-9"),
    )
    with pytest.raises(PackageValidationError):
        load_package(package_dir)
    assert await table_counts(content_session) == before

    package_dir = copy_fixture_package(tmp_path / "second")
    document = json.loads(chapter_file(package_dir, "ch02").read_text(encoding="utf-8"))
    rewrite_chapter(package_dir, "ch02", document["blocks"][:2])
    with pytest.raises(PackageValidationError):
        load_package(package_dir)
    assert await table_counts(content_session) == before


@pytest.mark.asyncio
async def test_fixture_content_can_never_be_published(content_session) -> None:
    package = load_package(FIXTURE_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    assert revision is not None

    await record_review(
        content_session,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    with pytest.raises(ContentReviewError):
        await publish_revision(content_session, revision_id=revision.id, actor="合成测试发布者")

    with pytest.raises(Exception) as trigger_error:
        await content_session.execute(
            text(
                "UPDATE content_chapter_review_states SET publication_status = 'PUBLISHED', "
                "published_by = '攻击者', published_at = now() WHERE revision_id = :rid"
            ),
            {"rid": revision.id},
        )
    assert "synthetic fixture" in str(trigger_error.value)
    await content_session.rollback()


@pytest.mark.asyncio
async def test_auto_validation_cannot_publish_and_draft_stays_draft(content_session) -> None:
    package = load_package(LEGACY_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    revision = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert revision is not None
    state = await record_review(
        content_session, revision_id=revision.id, status=ReviewStatus.AUTO_VALIDATED
    )
    assert state.review_status == ReviewStatus.AUTO_VALIDATED.value
    assert state.reviewer is None and state.reviewed_at is None
    assert state.publication_status == PublicationStatus.DRAFT.value
    with pytest.raises(ContentReviewError):
        await publish_revision(content_session, revision_id=revision.id, actor="合成测试发布者")

    await record_review(
        content_session,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    published_state = await publish_revision(
        content_session, revision_id=revision.id, actor="合成测试发布者"
    )
    assert published_state.publication_status == PublicationStatus.PUBLISHED.value
    assert published_state.published_by == "合成测试发布者"


@pytest.mark.asyncio
async def test_release_conflict_when_hash_changes(content_session, tmp_path: Path) -> None:
    package = load_package(FIXTURE_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    mutated = copy_fixture_package(tmp_path)
    document = json.loads(chapter_file(mutated, "ch01").read_text(encoding="utf-8"))
    rewrite_chapter(mutated, "ch01", document["blocks"])
    edit_json(
        course_file(mutated),
        lambda data: data["chapters"][0]["objectives"].append("新增目标让 manifest 变化"),
    )
    changed = load_package(mutated)
    from app.modules.content.importer import ContentImportError

    with pytest.raises(ContentImportError):
        await import_package(content_session, changed, dry_run=False)
    await content_session.rollback()


@pytest.mark.asyncio
async def test_materialize_published_refuses_draft(content_session, tmp_path: Path) -> None:
    from app.modules.content.importer import materialize_published

    package = load_package(FIXTURE_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    state = await record_review(
        content_session,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    chapter = next(item for item in package.chapters if item.spec.stable_slug == "ch01")
    with pytest.raises(ContentNotPublishable):
        materialize_published(tmp_path / "published", package, chapter, state)
    assert not (tmp_path / "published").exists()
