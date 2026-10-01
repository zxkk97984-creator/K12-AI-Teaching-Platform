from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.modules.content.importer import import_package
from app.modules.content.markdown_import import convert_markdown
from app.modules.content.models import ChapterReviewState, ChapterRevision, ContentProfile, Stage
from app.modules.content.package import load_package
from app.modules.content.schemas import BlockType, ViewerScope
from app.modules.content.service import visible_chapters

ROOT = Path(__file__).resolve().parents[2] / "curriculum/source/imported/computing-ai-md-v1"


def test_supplied_lectures_are_complete_and_reproducible(tmp_path):
    inventory = json.loads((ROOT / "inventory.json").read_text())
    source = tmp_path / "source"
    for relative, item in inventory["originals"].items():
        if relative.endswith("编码合并来源.md"):
            continue
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / item["archive"]).read_bytes())
    output = tmp_path / "converted"
    first = convert_markdown(source, output)
    assert first["courses"] == 20
    assert first["chapter_versions"] == 250
    assert convert_markdown(source, output) == first
    package = load_package(output)
    assert package.manifest_hash == load_package(ROOT).manifest_hash
    assert {item.spec.stage for item in package.chapters} == set(Stage)
    markdown = [
        block.text
        for chapter in package.chapters
        for block in chapter.blocks
        if block.type == BlockType.MARKDOWN
    ]
    assert all("\ufeff" not in text for text in markdown)
    assert any("```python" in text for text in markdown)
    assert any("|" in text and "---" in text for text in markdown)
    assert any("$" in text for text in markdown)
    assert all(".md)" not in text for text in markdown)

    changed = source / "初中/02-算法图解.md"
    changed.write_text(changed.read_text() + "\n版本更新测试：继续观察算法步骤。\n")
    second = convert_markdown(source, output)
    assert second["release_key"] != first["release_key"]
    assert load_package(output).chapters
    current = json.loads((output / "courses/junior-algorithms/course.json").read_text())
    assert all(chapter["revision"] == 2 for chapter in current["chapters"])
    assert list((output / "courses/junior-algorithms/chapters").glob("*-r1.json"))


@pytest.mark.asyncio
async def test_local_lecture_visibility_idempotency_and_withdrawal(content_session):
    package = load_package(ROOT)
    created = await import_package(content_session, package, dry_run=False)
    assert created.counters["courses_created"] == 20
    again = await import_package(content_session, package, dry_run=False)
    assert again.counters["revisions_created"] == 0
    assert await content_session.scalar(select(func.count()).select_from(ChapterRevision)) == 250
    for stage in Stage:
        local = await visible_chapters(
            content_session,
            ViewerScope(stage=stage, grade=None, profile=ContentProfile.DEVELOPMENT),
        )
        assert local and all(item.content_notice and not item.is_test_fixture for item in local)
        formal = await visible_chapters(
            content_session, ViewerScope(stage=stage, grade=None, profile=ContentProfile.FORMAL)
        )
        assert formal == []
    revision = await content_session.scalar(
        select(ChapterRevision).where(ChapterRevision.stage == "JUNIOR")
    )
    state = await content_session.get(ChapterReviewState, revision.id)
    state.publication_status = "WITHDRAWN"
    state.withdrawn_by = "test-admin"
    from datetime import UTC, datetime

    state.withdrawn_at = datetime.now(UTC)
    await content_session.commit()
    local = await visible_chapters(
        content_session,
        ViewerScope(stage=Stage.JUNIOR, grade=None, profile=ContentProfile.DEVELOPMENT),
    )
    assert revision.id not in {item.revision_id for item in local}
