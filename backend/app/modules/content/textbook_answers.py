"""Private, fixed textbook answers and locators in immutable chapter bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.book_import import STAGES, Answers, validate_books
from app.modules.content.importer import ContentImportError
from app.modules.content.markdown_import import headings, markdown_blocks
from app.modules.content.models import Chapter, ChapterRevision, Course, TextbookAnswer
from app.modules.content.package import (
    LoadedPackage,
    PackageValidationError,
    read_json,
    sha256_bytes,
)
from app.modules.content.schemas import SelfTestQuestionDTO

QUESTION_TYPES = {"单选题": "SINGLE_CHOICE", "简答题": "SHORT_ANSWER", "实践题": "PRACTICE"}


def question_locators(body: list[dict]) -> list[SelfTestQuestionDTO]:
    """Only the original textbook's self-test section establishes question IDs.

    Offsets are Python character offsets in a single block, at the next heading
    boundary. The client slices by Unicode code points, never by DOM text.
    """
    found: list[SelfTestQuestionDTO] = []
    in_self_test = False
    active: tuple[str, str] | None = None
    end: tuple[str, int] | None = None

    def finish() -> None:
        nonlocal active
        if active and end:
            found.append(
                SelfTestQuestionDTO(
                    question_id=active[0],
                    question_type=active[1],
                    end_block_id=end[0],
                    end_offset=end[1],
                    has_reference_answer=False,
                )
            )
        active = None

    for index, block in enumerate(body, 1):
        if block.get("type") != "MARKDOWN":
            continue
        text = block.get("text") or ""
        lines = text.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        block_id = f"b{index}"
        for line, level, title in headings(text):
            offset = offsets[line]
            if active and offset:
                end = (block_id, offset)
            if level <= 2:
                finish()
                in_self_test = level == 2 and title == "练习与自测"
            elif level == 3 and in_self_test:
                match = re.fullmatch(r"(Q0[1-6]) · (单选题|简答题|实践题)", title)
                if match:
                    finish()
                    active = (match[1], QUESTION_TYPES[match[2]])
        if active:
            end = (block_id, len(text))
    finish()
    if [(q.question_id, q.question_type) for q in found] != [
        (f"Q{i:02}", ["SINGLE_CHOICE", "SHORT_ANSWER", "PRACTICE"][(i - 1) // 2])
        for i in range(1, 7)
    ]:
        return []
    return found


@dataclass(frozen=True)
class AnswerBundle:
    course_slug: str
    chapter_slug: str
    revision: int
    source_hash: str
    answers: Answers


def validated_answer_bundles(package: LoadedPackage) -> list[AnswerBundle]:
    chapters = [
        c
        for c in package.chapters
        if c.course.textbook is not None or c.spec.source.conversion == "original-textbook-v1"
    ]
    if not chapters:
        return []
    source = validate_books(package.root / "source")
    report = source.report()
    if (
        package.release.release_key != f"original-books-v1-{report['source_hash'][:12]}"
        or read_json(package.root / "inventory.json", where="inventory") != report
    ):
        raise PackageValidationError("textbook source checksum differs from release")
    sources = {
        (f"book-{book.book_id}", chapter.order): (book, chapter)
        for book in source.manifest.books
        for chapter in book.chapters
    }
    bundles = []
    for item in chapters:
        pair = sources.get((item.course.stable_slug, item.spec.order_index))
        if pair is None:
            raise PackageValidationError("unknown textbook chapter identity")
        book, chapter = pair
        stages = (
            ["PRIMARY_LOWER", "PRIMARY_UPPER"]
            if book.stage_group == "PRIMARY"
            else [book.stage_group]
        )
        spec = item.spec
        raw = source.files[chapter.markdown_path]
        expected_blocks = [
            {"type": "TITLE", "text": chapter.title},
            {
                "type": "PARAGRAPH",
                "text": (
                    f"第 {chapter.order} 章 · 建议学习 {chapter.estimated_minutes} 分钟。"
                    "先读讲解，再完成活动与自测。"
                ),
            },
            *markdown_blocks(raw.decode().split("\n", 1)[1].lstrip()),
        ]
        body = [b.model_dump(mode="json", exclude_none=True) for b in item.blocks]
        if (
            spec.source.conversion != "original-textbook-v1"
            or spec.stage.value not in stages
            or (spec.grade_min, spec.grade_max) != STAGES[spec.stage.value]
            or spec.stable_slug
            != f"ch-{chapter.order:02}-{spec.stage.value.lower().replace('_', '-')}"
            or spec.title != chapter.title
            or spec.source.source_path != f"source/{chapter.markdown_path}"
            or spec.source.original_sha256 != sha256_bytes(raw)
            or item.course.textbook is None
            or item.course.textbook.book_id != book.book_id
            or body != expected_blocks
            or len(question_locators(body)) != 6
        ):
            raise PackageValidationError(
                "textbook chapter/stage/body does not match verified source"
            )
        answers = Answers.model_validate_json(source.files[chapter.answers_path])
        bundles.append(
            AnswerBundle(
                item.course.stable_slug,
                spec.stable_slug,
                spec.revision,
                sha256_bytes(source.files[chapter.answers_path]),
                answers,
            )
        )
    return bundles


async def plan_answers(
    db: AsyncSession, bundles: list[AnswerBundle]
) -> list[tuple[AnswerBundle, set[str]]]:
    """Check every existing answer before the importer writes any rows."""
    planned = []
    for bundle in bundles:
        rows = (
            await db.scalars(
                select(TextbookAnswer)
                .join(ChapterRevision)
                .join(Chapter)
                .join(Course)
                .where(
                    Course.stable_slug == bundle.course_slug,
                    Chapter.stable_slug == bundle.chapter_slug,
                    ChapterRevision.revision == bundle.revision,
                )
            )
        ).all()
        existing = {row.question_id: row for row in rows}
        for answer in bundle.answers.answers:
            row = existing.get(answer.question_id)
            if row and (
                row.source_hash != bundle.source_hash
                or row.question_type != answer.type
                or row.correct_options != answer.correct_options
                or row.reference_answer != answer.reference_answer
                or row.explanation != answer.explanation
            ):
                raise ContentImportError("existing textbook answer differs; use a new revision")
        planned.append((bundle, set(existing)))
    return planned


async def apply_answers(db: AsyncSession, planned: list[tuple[AnswerBundle, set[str]]]) -> None:
    for bundle, existing in planned:
        revision_id = await db.scalar(
            select(ChapterRevision.id)
            .join(Chapter)
            .join(Course)
            .where(
                Course.stable_slug == bundle.course_slug,
                Chapter.stable_slug == bundle.chapter_slug,
                ChapterRevision.revision == bundle.revision,
            )
        )
        for answer in bundle.answers.answers:
            if answer.question_id not in existing:
                db.add(
                    TextbookAnswer(
                        chapter_revision_id=revision_id,
                        question_id=answer.question_id,
                        question_type=answer.type,
                        correct_options=answer.correct_options,
                        reference_answer=answer.reference_answer,
                        explanation=answer.explanation,
                        source_hash=bundle.source_hash,
                    )
                )
    await db.flush()
