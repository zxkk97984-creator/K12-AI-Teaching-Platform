"""Validate the fixed book exchange format and adapt it to the existing importer.

The source is data, never executable. Answers remain in the private source tree;
only chapter Markdown and whitelisted book metadata enter student projections.
"""

from __future__ import annotations

import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field, HttpUrl

from app.modules.content.markdown_import import headings, markdown_blocks
from app.modules.content.package import (
    PackageValidationError,
    _validate,
    canonical_json,
    load_package,
    sha256_bytes,
    sha256_text,
)
from app.modules.content.schemas import ShortText, Slug, StrictModel, is_safe_relative_path

BOOKS = {
    "primary-computing": ("数字世界与计算思维", "PRIMARY", 1, 6, 1500),
    "primary-ai": ("和人工智能一起探索", "PRIMARY", 1, 6, 1500),
    "junior-python": ("Python 编程与问题解决", "JUNIOR", 7, 9, 2200),
    "junior-ai-data": ("从数据到人工智能", "JUNIOR", 7, 9, 2200),
    "senior-algorithms": ("数据结构与算法实践", "SENIOR", 10, 12, 2800),
    "senior-ai": ("机器学习原理与应用", "SENIOR", 10, 12, 2800),
}
HEADINGS = [
    "学习目标",
    "开始之前",
    "情景导入",
    "知识讲解",
    "详细示例",
    "动手实践",
    "常见误区",
    "练习与自测",
    "本章小结",
    "延伸阅读",
]
STAGES = {"PRIMARY_LOWER": (1, 3), "PRIMARY_UPPER": (4, 6), "JUNIOR": (7, 9), "SENIOR": (10, 12)}
HAN = re.compile(r"[\u4e00-\u9fff]")


class BookSourceModel(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Reference(BookSourceModel):
    title: ShortText
    url: HttpUrl
    purpose: ShortText


class BookChapter(BookSourceModel):
    chapter_id: Slug
    order: int = Field(ge=1, le=12)
    title: ShortText
    objectives: list[ShortText] = Field(min_length=3, max_length=5)
    prerequisite_chapter_ids: list[Slug] = Field(max_length=11)
    estimated_minutes: int = Field(ge=20, le=120)
    markdown_path: str
    answers_path: str
    knowledge_points: list[ShortText] = Field(min_length=3, max_length=6)
    references: list[Reference] = Field(max_length=12)


class Book(BookSourceModel):
    book_id: Slug
    title: ShortText
    stage_group: Literal["PRIMARY", "JUNIOR", "SENIOR"]
    grade_min: int
    grade_max: int
    description: str = Field(min_length=20, max_length=2000)
    prerequisites: list[ShortText] = Field(min_length=1, max_length=12)
    learning_outcomes: list[ShortText] = Field(min_length=1, max_length=12)
    preface_path: str
    chapters: list[BookChapter] = Field(min_length=12, max_length=12)


class BookManifest(BookSourceModel):
    schema_version: Literal["k12.book.source.v1"]
    package_id: Literal["k12-original-books-v1"]
    language: Literal["zh-CN"]
    content_kind: Literal["ORIGINAL_TEXTBOOK"]
    ai_assisted: Literal[True]
    review_status: Literal["UNREVIEWED"]
    books: list[Book] = Field(min_length=6, max_length=6)


class Rubric(BookSourceModel):
    criterion: str = Field(min_length=2, max_length=1000)
    points: int = Field(strict=True, gt=0, le=10)


class Answer(BookSourceModel):
    question_id: Literal["Q01", "Q02", "Q03", "Q04", "Q05", "Q06"]
    type: Literal["SINGLE_CHOICE", "SHORT_ANSWER", "PRACTICE"]
    correct_options: list[Literal["A", "B", "C", "D"]] = Field(max_length=1)
    reference_answer: str = Field(min_length=10, max_length=12000)
    explanation: str = Field(min_length=100, max_length=12000)
    rubric: list[Rubric] = Field(min_length=1, max_length=10)


class Answers(BookSourceModel):
    schema_version: Literal["k12.book.answers.v1"]
    book_id: Slug
    chapter_id: Slug
    answers: list[Answer] = Field(min_length=6, max_length=6)


class ChapterQuality(BookSourceModel):
    chapter_id: Slug
    body_han_chars: int = Field(ge=1)
    exercise_count: Literal[6]
    all_required_headings_present: bool
    answer_ids_match: bool
    code_examples_checked: bool


class Quality(BookSourceModel):
    schema_version: Literal["k12.book.quality.v1"]
    package_id: Literal["k12-original-books-v1"]
    book_count: Literal[6]
    chapter_count: Literal[72]
    answer_file_count: Literal[72]
    total_body_han_chars: int = Field(ge=156000)
    chapters: list[ChapterQuality] = Field(min_length=72, max_length=72)
    issues: list[str] = Field(max_length=50)


@dataclass(frozen=True)
class BookSource:
    manifest: BookManifest
    files: dict[str, bytes]
    counts: dict[str, int]

    def report(self) -> dict:
        return {
            "books": 6,
            "source_chapters": 72,
            "stage_versions": 96,
            "answer_files": 72,
            "files": len(self.files),
            "body_han_chars": sum(self.counts.values()),
            "book_body_han_chars": self.counts,
            "source_hash": sha256_text(
                canonical_json(
                    {path: sha256_bytes(raw) for path, raw in sorted(self.files.items())}
                )
            ),
        }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageValidationError(message)


def _json(raw: bytes, where: str) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise PackageValidationError("invalid UTF-8 JSON", where=where) from exc


def _markdown(raw: bytes, where: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise PackageValidationError("invalid UTF-8 Markdown", where=where) from exc
    _require("\ufeff" not in text and "\r" not in text, f"{where}: expected UTF-8 / LF")
    fence, prose, unit = None, [], []
    for line in text.splitlines():
        unit.append(line)
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if not marker:
            if fence is None:
                prose.append(line)
                if not line.strip():
                    _require(
                        len("\n".join(unit).strip()) <= 3500, f"{where}: oversized paragraph/fence"
                    )
                    unit = []
            continue
        if fence is None:
            _require(bool(marker[2].strip()), f"{where}: fenced code needs a language")
            fence = marker[1]
        elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
            fence = None
    _require(fence is None, f"{where}: unclosed fence")
    _require(len("\n".join(unit).strip()) <= 3500, f"{where}: oversized paragraph/fence")
    prose_text = re.sub(r"`[^`\n]+`", "", "\n".join(prose))
    _require(
        not re.search(r"</?[A-Za-z][^>]*>|!\[.*?\]\(", prose_text), f"{where}: HTML/image forbidden"
    )
    try:
        markdown_blocks(text)
    except ValueError as exc:
        raise PackageValidationError(str(exc), where=where) from exc
    return text


def body_han_count(text: str) -> int:
    section, fence, body = "", None, []
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence:
            continue
        if line.startswith("## "):
            section = line[3:].strip()
        if re.match(r"^\s{0,3}#{1,6}\s", line):
            continue
        if section not in {"练习与自测", "本章小结", "延伸阅读"}:
            body.append(line)
    return len(HAN.findall("\n".join(body)))


def validate_books(source_dir: Path, zip_path: Path | None = None) -> BookSource:
    """Read and validate *all* files before conversion or database access."""
    _require(not source_dir.is_symlink(), "source directory cannot be a symlink")
    files = {}
    for path in source_dir.rglob("*"):
        _require(not path.is_symlink(), "source contains a symlink")
        if path.is_dir():
            continue
        _require(path.is_file() and path.stat().st_size <= 2_000_000, "invalid/oversized file")
        relative = path.relative_to(source_dir).as_posix()
        _require(is_safe_relative_path(relative) and "\\" not in relative, "unsafe source path")
        files[relative] = path.read_bytes()
        _require(len(files) <= 153, "too many source files")
    _require(sum(map(len, files.values())) <= 20_000_000, "source exceeds size limit")
    _require("manifest.json" in files and "quality-report.json" in files, "missing manifest/report")
    manifest = _validate(BookManifest, _json(files["manifest.json"], "manifest"), where="manifest")
    quality = _validate(Quality, _json(files["quality-report.json"], "report"), where="report")
    _require({b.book_id for b in manifest.books} == set(BOOKS), "six fixed book IDs required")
    expected, counts, chapter_counts = {"manifest.json", "README.md", "quality-report.json"}, {}, {}
    for book in manifest.books:
        title, group, low, high, minimum = BOOKS[book.book_id]
        _require(
            (book.title, book.stage_group, book.grade_min, book.grade_max)
            == (title, group, low, high),
            f"book metadata mismatch: {book.book_id}",
        )
        _require(book.preface_path == f"books/{book.book_id}/preface.md", "unexpected preface path")
        expected.add(book.preface_path)
        _require(book.preface_path in files, f"missing preface: {book.book_id}")
        preface = _markdown(files[book.preface_path], book.preface_path)
        _require(600 <= len(HAN.findall(preface)) <= 1000, "preface length outside allowed bounds")
        seen, total = set(), 0
        for order, chapter in enumerate(book.chapters, 1):
            chapter_id = f"{book.book_id}-ch{order:02}"
            md = f"books/{book.book_id}/chapters/{order:02}.md"
            answer_path = f"answers/{book.book_id}/{order:02}.json"
            _require(
                (chapter.chapter_id, chapter.order, chapter.markdown_path, chapter.answers_path)
                == (chapter_id, order, md, answer_path),
                "chapter identity/path mismatch",
            )
            _require(set(chapter.prerequisite_chapter_ids) <= seen, "invalid prerequisite order")
            seen.add(chapter_id)
            expected.update((md, answer_path))
            _require(md in files and answer_path in files, f"missing chapter/answers: {chapter_id}")
            text = _markdown(files[md], md)
            _require(text.splitlines()[0] == f"# {chapter.title}", "chapter must start with its H1")
            all_headings = headings(text)
            _require(
                [t for _, level, t in all_headings if level == 1] == [chapter.title],
                f"H1 mismatch: {chapter_id}",
            )
            _require(
                [t for _, level, t in all_headings if level == 2] == HEADINGS,
                f"H2 mismatch: {chapter_id}",
            )
            count = body_han_count(text)
            _require(count >= minimum, f"body too short: {chapter_id}")
            chapter_counts[chapter_id] = count
            total += count
            exercises = text.split("## 练习与自测\n", 1)[1].split("## 本章小结", 1)[0]
            questions = re.split(r"(?m)^### (Q\d{2}) · (单选题|简答题|实践题)\s*$", exercises)
            _require(len(questions) == 19, f"six question headings required: {chapter_id}")
            answers = _validate(Answers, _json(files[answer_path], answer_path), where=answer_path)
            _require(
                (answers.book_id, answers.chapter_id) == (book.book_id, chapter_id),
                "answer ID mismatch",
            )
            for number, answer in enumerate(answers.answers, 1):
                label = ["单选题", "简答题", "实践题"][(number - 1) // 2]
                kind = ["SINGLE_CHOICE", "SHORT_ANSWER", "PRACTICE"][(number - 1) // 2]
                _require(
                    (answer.question_id, answer.type) == (f"Q{number:02}", kind),
                    "answer order/type mismatch",
                )
                _require(
                    questions[3 * number - 2 : 3 * number] == [answer.question_id, label],
                    "exercise IDs mismatch",
                )
                _require(
                    len(answer.correct_options) == (1 if number <= 2 else 0),
                    "invalid correct options",
                )
                if number <= 2:
                    options = re.findall(r"(?m)^\s*([A-D])[.．、)]\s*", questions[3 * number])
                    _require(
                        options == list("ABCD"),
                        f"four options required: {chapter_id}/{answer.question_id}",
                    )
                _require(sum(r.points for r in answer.rubric) == 10, "rubric must total 10")
                _require(len(HAN.findall(answer.explanation)) >= 100, "explanation too short")
        counts[book.book_id] = total
    _require(
        set(files) == expected, f"unexpected or missing files: {sorted(set(files) ^ expected)}"
    )
    _require(
        {c.chapter_id: c.body_han_chars for c in quality.chapters} == chapter_counts,
        "reported chapter counts differ from independent count",
    )
    _require(quality.total_body_han_chars == sum(counts.values()), "reported total differs")
    if zip_path:
        with zipfile.ZipFile(zip_path) as archive:
            zipped = {}
            for entry in archive.infolist():
                name = entry.filename
                _require(name.startswith("k12-original-books-v1/"), "unexpected ZIP root")
                relative = name.removeprefix("k12-original-books-v1/")
                if entry.is_dir():
                    _require(
                        not relative or is_safe_relative_path(relative.rstrip("/")),
                        "unsafe ZIP directory",
                    )
                    continue
                _require(
                    is_safe_relative_path(relative)
                    and "\\" not in relative
                    and relative not in zipped,
                    "unsafe/duplicate ZIP path",
                )
                _require(
                    not stat.S_ISLNK(entry.external_attr >> 16) and entry.file_size <= 2_000_000,
                    "unsafe ZIP entry",
                )
                _require(
                    relative in files and entry.file_size == len(files[relative]),
                    "ZIP inventory mismatch",
                )
                zipped[relative] = archive.read(entry)
            _require(zipped == files, "ZIP bytes differ from unpacked files")
    return BookSource(manifest, files, counts)


def convert_books(source_dir: Path, output_dir: Path, zip_path: Path | None = None) -> dict:
    source = validate_books(source_dir, zip_path)
    payloads = {f"source/{p}": raw for p, raw in source.files.items()}
    course_files = []
    for book in source.manifest.books:
        slug = f"book-{book.book_id}"
        course_path = f"courses/{slug}/course.json"
        course_files.append(course_path)
        points, specs = [], []
        for chapter in book.chapters:
            kp = []
            for i, name in enumerate(chapter.knowledge_points, 1):
                key = f"{slug}-ch{chapter.order:02}-kp{i}"
                kp.append(key)
                points.append(
                    {
                        "slug": key,
                        "name": name,
                        "topic": "计算机与人工智能",
                        "description": f"在「{chapter.title}」中学习{name}。",
                    }
                )
            stages = (
                ["PRIMARY_LOWER", "PRIMARY_UPPER"]
                if book.stage_group == "PRIMARY"
                else [book.stage_group]
            )
            body = source.files[chapter.markdown_path].decode()
            body = body.split("\n", 1)[1].lstrip()  # H1 is supplied by the reader.
            for stage in stages:
                chapter_slug = f"ch-{chapter.order:02}-{stage.lower().replace('_', '-')}"
                content_file = f"chapters/{chapter_slug}-r1.json"
                blocks = [
                    {"type": "TITLE", "text": chapter.title},
                    {
                        "type": "PARAGRAPH",
                        "text": (
                            f"第 {chapter.order} 章 · 建议学习 {chapter.estimated_minutes} 分钟。"
                            "先读讲解，再完成活动与自测。"
                        ),
                    },
                    *markdown_blocks(body),
                ]
                payloads[f"courses/{slug}/{content_file}"] = (
                    canonical_json(
                        {
                            "schema_version": "k12.content.chapter-blocks.v1",
                            "chapter": chapter_slug,
                            "revision": 1,
                            "blocks": blocks,
                            "observed_knowledge_point_marks": kp,
                        }
                    )
                    + "\n"
                ).encode()
                low, high = STAGES[stage]
                specs.append(
                    {
                        "stable_slug": chapter_slug,
                        "revision": 1,
                        "order_index": chapter.order,
                        "title": chapter.title,
                        "stage": stage,
                        "grade_min": low,
                        "grade_max": high,
                        "objectives": chapter.objectives,
                        "knowledge_points": kp,
                        "license_code": "PROJECT-ORIGINAL",
                        "license_notes": "用户提供的 AI 辅助原创教材，未经人工教学审校。",
                        "source": {
                            "source_commit": None,
                            "source_path": f"source/{chapter.markdown_path}",
                            "original_sha256": sha256_bytes(source.files[chapter.markdown_path]),
                            "conversion": "original-textbook-v1",
                        },
                        "content_file": content_file,
                    }
                )
        payloads[course_path] = (
            canonical_json(
                {
                    "schema_version": "k12.content.course.v1",
                    "stable_slug": slug,
                    "title": book.title,
                    "topic": "计算机与人工智能",
                    "description": book.description,
                    "knowledge_points": points,
                    "chapters": specs,
                    "textbook": {
                        "book_id": book.book_id,
                        "stage_group": book.stage_group,
                        "language": "zh-CN",
                        "ai_assisted": True,
                        "review_status": "UNREVIEWED",
                        "chapter_count": 12,
                        "body_han_chars": source.counts[book.book_id],
                        "prerequisites": book.prerequisites,
                        "learning_outcomes": book.learning_outcomes,
                        "preface": source.files[book.preface_path].decode(),
                    },
                }
            )
            + "\n"
        ).encode()
    report = source.report()
    release_key = f"original-books-v1-{report['source_hash'][:12]}"
    payloads["release.json"] = (
        canonical_json(
            {
                "schema_version": "k12.content.release.v1",
                "release_key": release_key,
                "source_kind": "NEW_SOURCE",
                "is_test_fixture": False,
                "local_demo_visible": True,
                "description": (
                    "六本原创专题教材，72 章正文；小学映射为低段和高段，共 96 个学段版本。"
                ),
                "license_code": "PROJECT-ORIGINAL",
                "license_notes": "AI 辅助原创教材，未经人工教学审校。",
                "course_files": course_files,
            }
        )
        + "\n"
    ).encode()
    payloads["inventory.json"] = (canonical_json(report) + "\n").encode()
    # A fixed v1 conversion is immutable: never overwrite differing existing bytes.
    for relative, raw in payloads.items():
        path = output_dir / relative
        _require(
            not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
            "symlink output path",
        )
        _require(
            not path.exists() or path.read_bytes() == raw,
            f"output differs: {relative}; use a new package version",
        )
    for relative, raw in payloads.items():
        path = output_dir / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    load_package(output_dir)
    return {**report, "release_key": release_key}
