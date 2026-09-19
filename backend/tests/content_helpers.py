from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.models import (
    Chapter,
    ChapterReviewState,
    ChapterRevision,
    Course,
    KnowledgePoint,
    ReadingEvent,
    Release,
    RevisionKnowledgePoint,
)
from app.modules.content.package import canonical_json

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_PACKAGE = REPO_ROOT / "curriculum/source/legacy/k12-library-696364f"
FIXTURE_PACKAGE = REPO_ROOT / "curriculum/source/synthetic/t06-fixtures-v1"
LEGACY_REPO = Path("/home/zxk/Projects/K12-Learning-platform")

CONTENT_TABLES = (
    "content_chapter_review_states",
    "content_revision_knowledge_points",
    "content_chapter_revisions",
    "content_chapters",
    "content_courses",
    "content_knowledge_points",
    "content_releases",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def copy_fixture_package(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(FIXTURE_PACKAGE, target)
    return target


def course_file(package: Path) -> Path:
    return package / "courses/t06-fixture-course/course.json"


def chapter_file(package: Path, chapter: str) -> Path:
    return package / "courses/t06-fixture-course/chapters" / f"{chapter}.json"


def edit_json(path: Path, mutate: Callable[[dict], None]) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def rewrite_chapter(package: Path, chapter: str, blocks: list[dict]) -> None:
    """Replace a chapter body and keep the declared source hash consistent."""

    path = chapter_file(package, chapter)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["blocks"] = blocks
    path.write_text(canonical_json(document) + "\n", encoding="utf-8")
    digest = sha256_bytes(path.read_bytes())
    course = course_file(package)
    edit_json(
        course,
        lambda data: next(item for item in data["chapters"] if item["stable_slug"] == chapter)[
            "source"
        ].__setitem__("original_sha256", digest),
    )


async def table_counts(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in (
        Release,
        Course,
        Chapter,
        ChapterRevision,
        KnowledgePoint,
        RevisionKnowledgePoint,
        ChapterReviewState,
        ReadingEvent,
    ):
        total = await session.scalar(select(func.count()).select_from(model))
        counts[model.__tablename__] = int(total or 0)
    return counts


async def revision_by_slug(
    session: AsyncSession, course_slug: str, chapter_slug: str, revision: int = 1
):
    return await session.scalar(
        select(ChapterRevision)
        .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .where(
            Course.stable_slug == course_slug,
            Chapter.stable_slug == chapter_slug,
            ChapterRevision.revision == revision,
        )
    )


async def review_state_for(session: AsyncSession, revision_id) -> ChapterReviewState:
    state = await session.scalar(
        select(ChapterReviewState).where(ChapterReviewState.revision_id == revision_id)
    )
    assert state is not None
    return state


def build_tiny_legacy_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a minimal read-only-style legacy tree used by converter tests."""

    root = tmp_path / "legacy"
    book_dir = root / "books/tiny-book"
    book_dir.mkdir(parents=True)
    chapter_md = (
        "<!-- meta\n"
        "chapter_title: 测试小章\n"
        "estimated_minutes: 10\n"
        "summary: 只用于转换器测试的合成章节。\n"
        "-->\n"
        "T: 测试小章\n"
        "\n"
        "P: 这是一段合成的测试正文，用来确认转换器可以处理标准标记并保留来源。\n"
        "KC: 测试卡片 :: 这是一张测试卡片，用来确认标题与正文被正确拆分成知识卡片。\n"
        "CALL: 想一想 :: 如果标记写错了，转换器应该直接失败还是悄悄跳过？\n"
    )
    (book_dir / "ch01.md").write_text(chapter_md, encoding="utf-8")
    (book_dir / "book.json").write_text(
        json.dumps(
            {
                "slug": "tiny-book",
                "title": "测试小书",
                "description": "只用于测试的合成书。",
                "grade_min": 7,
                "grade_max": 9,
                "license": "SYNTHETIC-FIXTURE",
                "chapters": [
                    {
                        "order": 1,
                        "file": "ch01.md",
                        "title": "测试小章",
                        "minutes": 10,
                        "summary": "只用于转换器测试的合成章节。",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    package = root / "package"
    course_dir = package / "courses/tiny-book"
    course_dir.mkdir(parents=True)
    (package / "release.json").write_text(
        json.dumps(
            {
                "schema_version": "k12.content.release.v1",
                "release_key": "synthetic-tiny-converter-test",
                "source_kind": "SYNTHETIC_FIXTURE",
                "is_test_fixture": True,
                "description": "转换器测试夹具。",
                "license_code": "SYNTHETIC-FIXTURE",
                "license_notes": "项目自造文本。",
                "course_files": ["courses/tiny-book/course.json"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    course_path = course_dir / "course.json"
    course_path.write_text(
        json.dumps(
            {
                "schema_version": "k12.content.course.v1",
                "stable_slug": "tiny-book",
                "title": "测试小书",
                "topic": "测试",
                "description": "只用于转换器测试的合成课程描述。",
                "knowledge_points": [
                    {
                        "slug": "tiny-point",
                        "name": "测试知识点",
                        "topic": "测试",
                        "description": "转换器测试用知识点。",
                    }
                ],
                "chapters": [
                    {
                        "stable_slug": "ch01",
                        "revision": 1,
                        "order_index": 1,
                        "title": "测试小章",
                        "stage": "JUNIOR",
                        "grade_min": 7,
                        "grade_max": 9,
                        "objectives": ["确认转换器可用"],
                        "knowledge_points": ["tiny-point"],
                        "license_code": "SYNTHETIC-FIXTURE",
                        "license_notes": "项目自造文本。",
                        "source": {
                            "source_commit": "0" * 40,
                            "source_path": "books/tiny-book/ch01.md",
                            "original_sha256": sha256_bytes((book_dir / "ch01.md").read_bytes()),
                            "conversion": "legacy-library-v1->k12.content.chapter-blocks.v1",
                        },
                        "content_file": "chapters/ch01.json",
                        "example_count": 0,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return root, package, course_path
