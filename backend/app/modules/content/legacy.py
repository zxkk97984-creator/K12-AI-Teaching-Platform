"""Strict converter from the read-only legacy library format to a source package.

Legacy chapters are Markdown-ish files with line markers (``T:``, ``P:``, ``KC:``,
``CALL:``, ``FIG:``, ``S:``, ``@kp=``) plus a ``book.json`` metadata file. The
converter is the only place that understands those markers. Anything it does not
understand is an error: a chapter is never partially converted.

``@kp=`` markers annotate individual blocks in the legacy format; the R1 content
schema keeps knowledge-point relations at chapter level, so the converter records
every observed mark and fails when a mark is not declared in the course file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.modules.content.package import (
    PackageValidationError,
    canonical_json,
    read_json,
    resolve_within,
    sha256_bytes,
)
from app.modules.content.schemas import (
    CHAPTER_CONTENT_SCHEMA_VERSION,
    BlockSpec,
    BlockType,
    ChapterSpec,
    CourseSpec,
)

META_KEYS = ("chapter_title", "estimated_minutes", "summary")
MARKER_RE = re.compile(r"^(T|P|KC|CALL|FIG): ")
KP_RE = re.compile(r"^@kp=([a-z0-9]+(?:-[a-z0-9]+)*)(?:,(.*))?$")
ASSET_REF_RE = re.compile(r"^assets/[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class LegacyChapter:
    blocks: tuple[BlockSpec, ...]
    meta: dict[str, str]
    observed_knowledge_point_marks: tuple[str, ...]


@dataclass(frozen=True)
class ConvertedChapter:
    course_slug: str
    chapter_slug: str
    revision: int
    content_file: str
    written: bool
    changed: bool
    observed_marks: tuple[str, ...]


def _fail(message: str, where: str) -> PackageValidationError:
    return PackageValidationError(message, where=where)


def parse_legacy_chapter(text: str, *, where: str) -> LegacyChapter:
    lines = [line.rstrip() for line in text.splitlines()]
    content = [line for line in lines if line.strip()]
    if not content or not content[0].strip().startswith("<!-- meta"):
        raise _fail("chapter must start with a <!-- meta --> comment", where)

    meta: dict[str, str] = {}
    index = 1
    closed = False
    while index < len(content):
        stripped = content[index].strip()
        if stripped == "-->":
            closed = True
            index += 1
            break
        if ":" not in stripped:
            raise _fail(f"meta line without key: {stripped!r}", where)
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key not in META_KEYS:
            raise _fail(f"unknown meta key {key!r}", where)
        meta[key] = value.strip()
        index += 1
    if not closed:
        raise _fail("meta comment is not closed with -->", where)
    missing = [key for key in META_KEYS if not meta.get(key)]
    if missing:
        raise _fail(f"meta is missing required keys: {missing}", where)
    try:
        minutes = int(meta["estimated_minutes"])
    except ValueError as exc:
        raise _fail("estimated_minutes must be an integer", where) from exc
    if not 1 <= minutes <= 240:
        raise _fail("estimated_minutes is out of range", where)

    blocks: list[BlockSpec] = []
    observed: list[str] = []
    pending_marks: list[str] = []
    section_index = 0

    def flush_marks() -> None:
        nonlocal pending_marks
        observed.extend(pending_marks)
        pending_marks = []

    for raw in content[index:]:
        line = raw.strip()
        if line.startswith("@kp="):
            match = KP_RE.match(line)
            if match is None:
                raise _fail(f"invalid @kp marker: {line!r}", where)
            if not blocks:
                raise _fail("@kp marker must follow a content block", where)
            pending_marks.append(match.group(1))
            continue
        flush_marks()
        if line.startswith("S:"):
            label = line[2:].strip()
            if not label:
                raise _fail("S: section label cannot be empty", where)
            section_index += 1
            blocks.append(
                BlockSpec(type=BlockType.SECTION, key=f"section-{section_index}", text=label)
            )
            continue
        if not MARKER_RE.match(line):
            raise _fail(f"unknown or unsupported marker: {line[:60]!r}", where)
        kind = line.split(":", 1)[0]
        payload = line[len(kind) + 1 :].strip()
        if not payload:
            raise _fail(f"{kind}: block content cannot be empty", where)
        if kind == "T":
            blocks.append(BlockSpec(type=BlockType.TITLE, text=payload))
        elif kind == "P":
            if "|mark:" in payload:
                body, _, mark = payload.rpartition("|mark:")
                blocks.append(
                    BlockSpec(type=BlockType.PARAGRAPH, text=body.strip(), mark=mark.strip())
                )
            else:
                blocks.append(BlockSpec(type=BlockType.PARAGRAPH, text=payload))
        elif kind == "KC":
            segments = [segment.strip() for segment in payload.split("::")]
            if not segments[0] or len(segments) < 2 or not segments[1]:
                raise _fail("KC requires 'title :: text' with non-empty parts", where)
            example = None
            if len(segments) >= 4 and segments[2] and segments[3]:
                example = {"label": segments[2], "text": segments[3]}
            blocks.append(
                BlockSpec(
                    type=BlockType.KNOWLEDGE_CARD,
                    title=segments[0],
                    text=segments[1],
                    example=example,
                )
            )
        elif kind == "CALL":
            title, _, body = payload.partition("::")
            if not title.strip() or not body.strip():
                raise _fail("CALL requires 'title :: text' with non-empty parts", where)
            blocks.append(BlockSpec(type=BlockType.CALLOUT, title=title.strip(), text=body.strip()))
        elif kind == "FIG":
            alt, _, rest = payload.partition("::")
            caption = rest.strip()
            src = None
            if "::" in rest:
                head, _, tail = rest.rpartition("::")
                candidate = tail.strip()
                if ASSET_REF_RE.match(candidate):
                    src = candidate
                    caption = head.strip().rstrip(":").strip() or caption
            if not alt.strip() or not caption:
                raise _fail("FIG requires 'alt :: caption'", where)
            blocks.append(
                BlockSpec(type=BlockType.FIGURE, alt=alt.strip(), caption=caption, src=src)
            )
    flush_marks()
    if not blocks or blocks[0].type is not BlockType.TITLE:
        raise _fail("chapter must start with a T: title block", where)
    return LegacyChapter(
        blocks=tuple(blocks),
        meta=meta,
        observed_knowledge_point_marks=tuple(sorted(set(observed))),
    )


def _load_book_json(source_path: Path, *, where: str) -> dict:
    book_file = source_path.parent / "book.json"
    payload = read_json(book_file, where=f"{where}:book.json")
    if not isinstance(payload, dict):
        raise _fail("book.json must be an object", where)
    return payload


def _verify_against_book(
    book: dict, course: CourseSpec, spec: ChapterSpec, meta: dict[str, str], *, where: str
) -> None:
    if book.get("slug") != course.stable_slug:
        raise _fail(
            f"book.json slug {book.get('slug')!r} does not match course {course.stable_slug}", where
        )
    if (book.get("grade_min"), book.get("grade_max")) != (spec.grade_min, spec.grade_max):
        raise _fail("book.json grade range does not match the course file", where)
    license_code = str(book.get("license", "")).strip()
    if license_code and license_code.lower() != spec.license_code.value.lower():
        raise _fail(
            f"book.json license {license_code!r} does not match {spec.license_code.value}", where
        )
    chapters = book.get("chapters") or []
    source_name = Path(spec.source.source_path).name
    entry = next((item for item in chapters if item.get("file") == source_name), None)
    if entry is None:
        raise _fail(f"book.json has no chapter entry for {source_name}", where)
    if entry.get("title") != meta["chapter_title"] or entry.get("title") != spec.title:
        raise _fail("chapter title differs between book.json, meta and the course file", where)
    if str(entry.get("minutes")) != meta["estimated_minutes"]:
        raise _fail("chapter minutes differ between book.json and meta", where)
    if entry.get("summary") != meta["summary"]:
        raise _fail("chapter summary differs between book.json and meta", where)


def convert_course(
    course_file: Path,
    *,
    legacy_root: Path,
    check_only: bool = False,
) -> list[ConvertedChapter]:
    """Convert one course file's chapters from the read-only legacy tree."""

    course_relative = str(course_file)
    payload = read_json(course_file, where=course_relative)
    try:
        course = CourseSpec.model_validate(payload)
    except Exception as exc:  # pragma: no cover - surfaced with a clear message
        raise _fail(f"course file is invalid: {exc}", course_relative) from exc

    results: list[ConvertedChapter] = []
    for spec in course.chapters:
        where = f"{course_relative}:{spec.stable_slug}"
        source_file = resolve_within(legacy_root, spec.source.source_path, where=where)
        if not source_file.is_file():
            raise _fail(f"declared source file is missing: {spec.source.source_path}", where)
        original = source_file.read_bytes()
        if sha256_bytes(original) != spec.source.original_sha256:
            raise _fail("declared original_sha256 does not match the legacy source file", where)
        book = _load_book_json(source_file, where=where)
        chapter = parse_legacy_chapter(original.decode("utf-8"), where=where)
        _verify_against_book(book, course, spec, chapter.meta, where=where)
        unknown_marks = set(chapter.observed_knowledge_point_marks) - set(spec.knowledge_points)
        if unknown_marks:
            raise _fail(
                f"@kp marks are not declared in the course file: {sorted(unknown_marks)}", where
            )

        content_path = resolve_within(course_file.parent, spec.content_file, where=where)
        document = {
            "schema_version": CHAPTER_CONTENT_SCHEMA_VERSION,
            "chapter": spec.stable_slug,
            "revision": spec.revision,
            "blocks": [
                block.model_dump(mode="json", exclude_none=True) for block in chapter.blocks
            ],
            "legacy_meta": {
                "chapter_title": chapter.meta["chapter_title"],
                "estimated_minutes": int(chapter.meta["estimated_minutes"]),
                "summary": chapter.meta["summary"],
            },
            "observed_knowledge_point_marks": sorted(chapter.observed_knowledge_point_marks),
        }
        rendered = canonical_json(document) + "\n"
        existing = content_path.read_text(encoding="utf-8") if content_path.is_file() else None
        changed = existing != rendered
        if check_only:
            if changed:
                raise _fail(
                    f"converted content differs from {spec.content_file}; run without --check",
                    where,
                )
            written = False
        else:
            if changed:
                content_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = content_path.with_suffix(content_path.suffix + ".tmp")
                temporary.write_text(rendered, encoding="utf-8")
                temporary.replace(content_path)
            written = changed
        results.append(
            ConvertedChapter(
                course_slug=course.stable_slug,
                chapter_slug=spec.stable_slug,
                revision=spec.revision,
                content_file=str(content_path),
                written=written,
                changed=changed,
                observed_marks=chapter.observed_knowledge_point_marks,
            )
        )
    return results
