from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.content.importer import import_package
from app.modules.content.models import ContentProfile, ReviewStatus
from app.modules.content.package import load_package
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import (
    FIXTURE_NOTICE,
    publish_revision,
    record_review,
    visible_chapter_detail,
    visible_chapters,
    withdraw_revision,
)
from app.modules.identity.models import Stage
from tests.content_helpers import (
    FIXTURE_PACKAGE,
    LEGACY_PACKAGE,
    copy_fixture_package,
    course_file,
    edit_json,
    revision_by_slug,
)


def _dev(stage: Stage, grade: int | None = None) -> ViewerScope:
    return ViewerScope(stage=stage, grade=grade, profile=ContentProfile.DEVELOPMENT)


def _formal(stage: Stage, grade: int | None = None) -> ViewerScope:
    return ViewerScope(stage=stage, grade=grade, profile=ContentProfile.FORMAL)


@pytest.mark.asyncio
async def test_unreviewed_draft_is_hidden_and_withdrawal_hides_published(content_session) -> None:
    package = load_package(LEGACY_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    junior = _dev(Stage.JUNIOR, 8)

    assert await visible_chapters(content_session, junior) == []
    revision = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert revision is not None
    assert (
        await visible_chapter_detail(content_session, chapter_id=revision.chapter_id, viewer=junior)
        is None
    )

    await record_review(
        content_session,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
        comment="仅用于自动化测试的审校记录",
    )
    await publish_revision(content_session, revision_id=revision.id, actor="合成测试发布者")

    visible = await visible_chapters(content_session, junior)
    assert [item.chapter_slug for item in visible] == ["ch05"]
    assert visible[0].revision == 1
    assert visible[0].content_notice is None

    detail = await visible_chapter_detail(
        content_session, chapter_id=revision.chapter_id, viewer=junior
    )
    assert detail is not None
    assert detail.objectives
    assert [item.slug for item in detail.knowledge_points] == [
        "variable",
        "condition-if",
        "loop",
        "random-number",
    ]
    assert detail.blocks[0].type.value == "TITLE"

    # The senior chapter is out of stage even though it is in the same release.
    senior = _dev(Stage.SENIOR, 11)
    assert [item.chapter_slug for item in await visible_chapters(content_session, senior)] == []

    await withdraw_revision(
        content_session,
        revision_id=revision.id,
        actor="合成测试发布者",
        comment="撤回后不应再被学生读到",
    )
    assert await visible_chapters(content_session, junior) == []
    assert (
        await visible_chapter_detail(content_session, chapter_id=revision.chapter_id, viewer=junior)
        is None
    )
    assert (
        await visible_chapter_detail(
            content_session, chapter_id=revision.chapter_id, viewer=junior, revision=1
        )
        is None
    )


@pytest.mark.asyncio
async def test_fixtures_visible_only_in_development_and_always_labelled(content_session) -> None:
    package = load_package(FIXTURE_PACKAGE)
    await import_package(content_session, package, dry_run=False)

    junior_dev = await visible_chapters(content_session, _dev(Stage.JUNIOR, 8))
    assert [item.chapter_slug for item in junior_dev] == ["ch02"]
    assert junior_dev[0].is_test_fixture is True
    assert junior_dev[0].content_notice == FIXTURE_NOTICE
    assert junior_dev[0].publication_status.value == "DRAFT"
    assert junior_dev[0].review_status is ReviewStatus.UNREVIEWED

    assert await visible_chapters(content_session, _formal(Stage.JUNIOR, 8)) == []
    assert await visible_chapters(content_session, _formal(Stage.PRIMARY_LOWER, 2)) == []

    lower_dev = await visible_chapters(content_session, _dev(Stage.PRIMARY_LOWER, 2))
    assert [item.chapter_slug for item in lower_dev] == ["ch01"]
    assert lower_dev[0].content_notice == FIXTURE_NOTICE


@pytest.mark.asyncio
async def test_grade_null_keeps_stage_semantics_and_explicit_range_filters(content_session) -> None:
    package = load_package(FIXTURE_PACKAGE)
    await import_package(content_session, package, dry_run=False)

    # ch02 declares no grade range: it matches any grade in the stage, including "unknown".
    assert [
        item.chapter_slug for item in await visible_chapters(content_session, _dev(Stage.JUNIOR))
    ] == ["ch02"]
    assert [
        item.chapter_slug for item in await visible_chapters(content_session, _dev(Stage.JUNIOR, 8))
    ] == ["ch02"]

    # A stage without any declared grade still needs a stage to read anything.
    with pytest.raises(ValueError):
        ViewerScope(stage=None, grade=3, profile=ContentProfile.DEVELOPMENT)
    assert await visible_chapters(content_session, ViewerScope(stage=None, grade=None)) == []


@pytest.mark.asyncio
async def test_explicit_grade_range_outside_student_grade_is_hidden(
    content_session, tmp_path: Path
) -> None:
    package_dir = copy_fixture_package(tmp_path)
    edit_json(
        course_file(package_dir), lambda data: data["chapters"][1].__setitem__("grade_min", 7)
    )
    edit_json(
        course_file(package_dir), lambda data: data["chapters"][1].__setitem__("grade_max", 7)
    )
    package = load_package(package_dir)
    await import_package(content_session, package, dry_run=False)

    assert [
        item.chapter_slug for item in await visible_chapters(content_session, _dev(Stage.JUNIOR, 7))
    ] == ["ch02"]
    assert await visible_chapters(content_session, _dev(Stage.JUNIOR, 8)) == []


@pytest.mark.asyncio
async def test_new_revision_does_not_replace_published_version_until_released(
    content_session, tmp_path: Path
) -> None:
    import json
    import shutil

    package = load_package(LEGACY_PACKAGE)
    await import_package(content_session, package, dry_run=False)
    junior = _dev(Stage.JUNIOR, 8)

    first = await revision_by_slug(content_session, "python-first-steps", "ch05", 1)
    assert first is not None
    first_body = json.dumps(first.body, ensure_ascii=False, sort_keys=True)
    await record_review(
        content_session,
        revision_id=first.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    await publish_revision(content_session, revision_id=first.id, actor="合成测试发布者")
    assert (await visible_chapters(content_session, junior))[0].revision == 1

    # A drafted second revision lives in its own release and stays invisible.
    revised_dir = tmp_path / "revised"
    shutil.copytree(LEGACY_PACKAGE, revised_dir)
    edit_json(
        revised_dir / "release.json",
        lambda data: data.__setitem__("release_key", "legacy-k12-696364f-r2-draft"),
    )

    def bump(data: dict) -> None:
        chapter = next(item for item in data["chapters"] if item["stable_slug"] == "ch05")
        chapter["revision"] = 2

    edit_json(revised_dir / "courses/python-first-steps/course.json", bump)
    chapter_path = revised_dir / "courses/python-first-steps/chapters/ch05.json"
    document = json.loads(chapter_path.read_text(encoding="utf-8"))
    document["revision"] = 2
    document["blocks"][0]["text"] = "小项目：猜数字游戏（第二版草稿）"
    chapter_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    revised = load_package(revised_dir)
    result = await import_package(content_session, revised, dry_run=False)
    assert result.counters["revisions_created"] == 1

    visible = await visible_chapters(content_session, junior)
    assert [item.revision for item in visible] == [1]

    second = await revision_by_slug(content_session, "python-first-steps", "ch05", 2)
    assert second is not None
    await record_review(
        content_session,
        revision_id=second.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="合成测试审校者",
    )
    await publish_revision(content_session, revision_id=second.id, actor="合成测试发布者")
    assert [item.revision for item in await visible_chapters(content_session, junior)] == [2]

    # The old revision is still readable by explicit revision and was not mutated.
    rolled_back = await visible_chapter_detail(
        content_session, chapter_id=first.chapter_id, viewer=junior, revision=1
    )
    assert rolled_back is not None
    assert rolled_back.revision == 1
    rolled_back_body = [
        {
            key: value
            for key, value in block.model_dump(mode="json", exclude_none=True).items()
            if key != "block_id"
        }
        for block in rolled_back.blocks
    ]
    assert json.dumps(rolled_back_body, ensure_ascii=False, sort_keys=True) == first_body
