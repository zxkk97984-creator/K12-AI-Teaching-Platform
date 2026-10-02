from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.modules.content.book_import import convert_books, validate_books
from app.modules.content.importer import import_package
from app.modules.content.markdown_import import headings
from app.modules.content.models import ChapterRevision, ContentProfile, Stage
from app.modules.content.package import PackageValidationError, load_package, revision_snapshot
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import visible_courses
from tests.identity_helpers import create_synthetic_user, login

ROOT = Path(__file__).resolve().parents[2] / "curriculum/source/original/original-books-v1"
SOURCE = ROOT / "source"


def test_book_source_counts_and_conversion_are_reproducible(tmp_path):
    report = validate_books(SOURCE).report()
    assert report["files"] == 153
    assert report["body_han_chars"] == 311590
    first = convert_books(SOURCE, tmp_path / "converted")
    assert convert_books(SOURCE, tmp_path / "converted") == first
    package = load_package(tmp_path / "converted")
    assert package.manifest_hash == load_package(ROOT).manifest_hash
    assert len(package.chapters) == 96
    assert {chapter.spec.stage for chapter in package.chapters} == set(Stage)
    for chapter in package.chapters:
        assert chapter.course.textbook.chapter_count == 12
        public = json.dumps(revision_snapshot(package, chapter), ensure_ascii=False)
        assert '"reference_answer"' not in public and '"correct_options"' not in public
        assert "answers/" not in public
        body = "\n".join(block.text or "" for block in chapter.blocks)
        assert "## 练习与自测" in body and "### Q06 · 实践题" in body
        assert not any(level == 1 for _, level, _ in headings(body))


@pytest.mark.parametrize("mutation", ["path", "extra_field", "answer", "count", "html"])
def test_invalid_book_package_is_rejected_before_output(tmp_path, mutation):
    source = tmp_path / "source"
    shutil.copytree(SOURCE, source)
    if mutation in {"path", "extra_field"}:
        file = source / "manifest.json"
        data = json.loads(file.read_text())
        if mutation == "path":
            data["books"][0]["chapters"][0]["answers_path"] = "../../secret.json"
        else:
            data["books"][0]["instructions"] = "unexpected external instruction"
        file.write_text(json.dumps(data, ensure_ascii=False))
    elif mutation == "answer":
        file = source / "answers/primary-computing/01.json"
        data = json.loads(file.read_text())
        data["answers"][0]["rubric"][0]["points"] = 1
        file.write_text(json.dumps(data, ensure_ascii=False))
    elif mutation == "count":
        file = source / "quality-report.json"
        data = json.loads(file.read_text())
        data["total_body_han_chars"] += 1
        file.write_text(json.dumps(data, ensure_ascii=False))
    else:
        file = source / "books/primary-computing/chapters/01.md"
        file.write_text(file.read_text() + "\n<iframe src='https://example.com'></iframe>\n")
    output = tmp_path / "converted"
    with pytest.raises(PackageValidationError):
        convert_books(source, output)
    assert not output.exists()


def test_symlinks_and_changed_existing_conversions_are_rejected(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(SOURCE, source)
    file = source / "README.md"
    file.unlink()
    file.symlink_to(SOURCE / "README.md")
    with pytest.raises(PackageValidationError, match="symlink"):
        validate_books(source)
    output = tmp_path / "converted"
    convert_books(SOURCE, output)
    release = output / "release.json"
    release.write_text("{}")
    with pytest.raises(PackageValidationError, match="output differs"):
        convert_books(SOURCE, output)
    assert release.read_text() == "{}"


@pytest.mark.asyncio
async def test_import_is_idempotent_and_all_four_stages_see_two_complete_books(content_session):
    package = load_package(ROOT)
    created = await import_package(content_session, package, dry_run=False)
    assert created.counters["courses_created"] == 6
    assert created.counters["revisions_created"] == 96
    again = await import_package(content_session, package, dry_run=False)
    assert again.counters["revisions_created"] == 0
    assert await content_session.scalar(select(func.count()).select_from(ChapterRevision)) == 96
    for stage in Stage:
        viewer = ViewerScope(stage=stage, grade=None, profile=ContentProfile.DEVELOPMENT)
        books = await visible_courses(content_session, viewer)
        assert len(books) == 2 and all(len(book.chapters) == 12 for book in books)
        for book in books:
            assert book.textbook and book.textbook.body_han_chars >= 18000
            assert [c.order_index for c in book.chapters] == list(range(1, 13))
            assert all(c.stage == stage and not c.is_test_fixture for c in book.chapters)
            assert all("原创教材" in c.content_notice for c in book.chapters)
        formal = ViewerScope(stage=stage, grade=None, profile=ContentProfile.FORMAL)
        assert await visible_courses(content_session, formal) == []


@pytest.mark.asyncio
async def test_student_book_catalog_reader_and_answer_isolation(
    content_session, client, test_settings
):
    await import_package(content_session, load_package(ROOT), dry_run=False)
    await create_synthetic_user(
        test_settings, username="book.junior", password="synthetic-pass-1", stage="JUNIOR", grade=8
    )
    assert (await login(client, "book.junior", "synthetic-pass-1")).status_code == 200
    catalog = await client.get("/api/v1/learning/catalog")
    assert catalog.status_code == 200
    items = catalog.json()["items"]
    books = [item for item in items if item["is_textbook"]]
    assert len(books) == 2 and all(item["chapter_count"] == 12 for item in books)
    for book in books:
        course = await client.get(f"/api/v1/courses/{book['id']}")
        assert course.status_code == 200
        assert course.json()["textbook"]["preface"]
        for chapter in course.json()["chapters"]:
            response = await client.get(f"/api/v1/chapters/{chapter['chapter_id']}")
            assert response.status_code == 200
            assert '"reference_answer"' not in response.text
            assert '"correct_options"' not in response.text
            assert "answers/" not in response.text
    senior = await visible_courses(
        content_session,
        ViewerScope(stage=Stage.SENIOR, grade=11, profile=ContentProfile.DEVELOPMENT),
    )
    assert (
        await client.get(f"/api/v1/chapters/{senior[0].chapters[0].chapter_id}")
    ).status_code == 404
