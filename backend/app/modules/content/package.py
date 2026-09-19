"""Load and validate a curriculum source package (data only, never executed)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.modules.content.schemas import (
    BlockSpec,
    BlockType,
    ChapterSpec,
    CourseSpec,
    KnowledgePointSpec,
    ReleaseSpec,
)


class PackageValidationError(Exception):
    """The package is not safe or not well formed; nothing may be written."""

    def __init__(self, message: str, *, where: str | None = None) -> None:
        super().__init__(f"{where}: {message}" if where else message)
        self.where = where


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def resolve_within(root: Path, relative: str, *, where: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise PackageValidationError("path escapes the package directory", where=where)
    return candidate


def read_json(path: Path, *, where: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackageValidationError("file is missing", where=where) from exc
    except json.JSONDecodeError as exc:
        raise PackageValidationError(f"invalid JSON: {exc}", where=where) from exc


def _validate(model, payload: Any, *, where: str):  # noqa: ANN001 - small internal helper
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ())) or "<root>"
        raise PackageValidationError(
            f"{first.get('msg', 'invalid value')} at {location}", where=where
        ) from exc


@dataclass(frozen=True)
class LoadedChapter:
    course: CourseSpec
    spec: ChapterSpec
    blocks: tuple[BlockSpec, ...]
    knowledge_points: tuple[KnowledgePointSpec, ...]
    content_hash: str


@dataclass(frozen=True)
class LoadedPackage:
    root: Path
    release: ReleaseSpec
    chapters: tuple[LoadedChapter, ...]
    manifest_hash: str


def content_hash_for(
    spec: ChapterSpec,
    blocks: tuple[BlockSpec, ...],
    knowledge_points: tuple[KnowledgePointSpec, ...],
) -> str:
    payload = {
        "chapter": spec.stable_slug,
        "revision": spec.revision,
        "stage": spec.stage.value,
        "grade_min": spec.grade_min,
        "grade_max": spec.grade_max,
        "objectives": list(spec.objectives),
        "knowledge_points": [item.slug for item in knowledge_points],
        "license_code": spec.license_code.value,
        "source": spec.source.model_dump(mode="json"),
        "blocks": [block.model_dump(mode="json", exclude_none=True) for block in blocks],
    }
    return sha256_text(canonical_json(payload))


def manifest_hash_for(release: ReleaseSpec, chapters: tuple[LoadedChapter, ...]) -> str:
    payload = {
        "release_key": release.release_key,
        "source_kind": release.source_kind.value,
        "is_test_fixture": release.is_test_fixture,
        "courses": [
            {
                "slug": chapter.course.stable_slug,
                "chapter": chapter.spec.stable_slug,
                "revision": chapter.spec.revision,
                "content_hash": chapter.content_hash,
            }
            for chapter in chapters
        ],
    }
    return sha256_text(canonical_json(payload))


def _load_blocks(path: Path, *, where: str) -> tuple[tuple[BlockSpec, ...], dict, list[str]]:
    payload = read_json(path, where=where)
    if not isinstance(payload, dict):
        raise PackageValidationError("chapter content file must be a JSON object", where=where)
    allowed = {
        "schema_version",
        "chapter",
        "revision",
        "blocks",
        "legacy_meta",
        "observed_knowledge_point_marks",
    }
    extra = set(payload) - allowed
    if extra:
        raise PackageValidationError(f"unknown chapter content keys: {sorted(extra)}", where=where)
    if payload.get("schema_version") != "k12.content.chapter-blocks.v1":
        raise PackageValidationError("unsupported chapter content schema_version", where=where)
    raw_blocks = payload.get("blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise PackageValidationError("blocks must be a non-empty list", where=where)
    blocks = tuple(
        _validate(BlockSpec, item, where=f"{where}#{index}")
        for index, item in enumerate(raw_blocks)
    )
    if blocks[0].type is not BlockType.TITLE:
        raise PackageValidationError("the first block must be a TITLE block", where=where)
    if len(blocks) < 3:
        raise PackageValidationError("a chapter needs at least three blocks", where=where)
    if not any(block.type is BlockType.PARAGRAPH for block in blocks):
        raise PackageValidationError("a chapter needs at least one PARAGRAPH block", where=where)
    previous: str | None = None
    for block in blocks:
        if block.text is not None and block.text == previous:
            raise PackageValidationError(
                "adjacent blocks must not repeat the same text", where=where
            )
        previous = block.text
    marks = payload.get("observed_knowledge_point_marks") or []
    if not isinstance(marks, list) or not all(isinstance(item, str) for item in marks):
        raise PackageValidationError(
            "observed_knowledge_point_marks must be a list of strings", where=where
        )
    return blocks, payload, list(marks)


def load_package(release_dir: Path, *, legacy_root: Path | None = None) -> LoadedPackage:
    """Load and validate every file of a package before any database write."""

    root = release_dir.resolve()
    if not root.is_dir():
        raise PackageValidationError("release directory does not exist", where=str(root))
    release_payload = read_json(root / "release.json", where="release.json")
    release = _validate(ReleaseSpec, release_payload, where="release.json")

    loaded: list[LoadedChapter] = []
    for course_relative in release.course_files:
        course_path = resolve_within(root, course_relative, where=course_relative)
        course_payload = read_json(course_path, where=course_relative)
        course = _validate(CourseSpec, course_payload, where=course_relative)
        if course.stable_slug not in course_relative:
            raise PackageValidationError(
                f"course file {course_relative} does not belong to course {course.stable_slug}",
                where=course_relative,
            )
        kp_by_slug = {item.slug: item for item in course.knowledge_points}
        for spec in course.chapters:
            content_path = resolve_within(
                course_path.parent, spec.content_file, where=f"{course_relative}:{spec.stable_slug}"
            )
            blocks, content_document, observed_marks = _load_blocks(
                content_path, where=f"{course_relative}:{spec.stable_slug}"
            )
            if content_document.get("chapter") != spec.stable_slug:
                raise PackageValidationError(
                    f"content file declares chapter {content_document.get('chapter')!r} "
                    f"but the course file declares {spec.stable_slug!r}",
                    where=f"{course_relative}:{spec.stable_slug}",
                )
            if content_document.get("revision") != spec.revision:
                raise PackageValidationError(
                    "content file revision does not match the course file revision",
                    where=f"{course_relative}:{spec.stable_slug}",
                )
            unknown_marks = set(observed_marks) - set(spec.knowledge_points)
            if unknown_marks:
                raise PackageValidationError(
                    f"source marks reference undeclared knowledge points: {sorted(unknown_marks)}",
                    where=f"{course_relative}:{spec.stable_slug}",
                )
            for block in blocks:
                if block.src is not None:
                    asset = resolve_within(
                        root, block.src, where=f"{course_relative}:{spec.stable_slug}"
                    )
                    if not asset.is_file():
                        raise PackageValidationError(
                            f"figure asset is missing: {block.src}",
                            where=f"{course_relative}:{spec.stable_slug}",
                        )
            if legacy_root is not None and spec.source.source_path:
                source_file = resolve_within(
                    legacy_root,
                    spec.source.source_path,
                    where=f"{course_relative}:{spec.stable_slug}",
                )
                if not source_file.is_file():
                    raise PackageValidationError(
                        f"declared source file is missing: {spec.source.source_path}",
                        where=f"{course_relative}:{spec.stable_slug}",
                    )
                actual = sha256_bytes(source_file.read_bytes())
                if actual != spec.source.original_sha256:
                    raise PackageValidationError(
                        "declared original_sha256 does not match the source file",
                        where=f"{course_relative}:{spec.stable_slug}",
                    )
            knowledge_points = tuple(kp_by_slug[slug] for slug in spec.knowledge_points)
            loaded.append(
                LoadedChapter(
                    course=course,
                    spec=spec,
                    blocks=blocks,
                    knowledge_points=knowledge_points,
                    content_hash=content_hash_for(spec, blocks, knowledge_points),
                )
            )
    # Deterministic order: course slug, then chapter order.
    loaded.sort(
        key=lambda item: (item.course.stable_slug, item.spec.order_index, item.spec.stable_slug)
    )
    chapters = tuple(loaded)
    return LoadedPackage(
        root=root,
        release=release,
        chapters=chapters,
        manifest_hash=manifest_hash_for(release, chapters),
    )


def revision_snapshot(package: LoadedPackage, chapter: LoadedChapter) -> dict[str, Any]:
    """Canonical immutable snapshot written to the on-disk release mirror."""

    return {
        "schema_version": "k12.content.revision-snapshot.v1",
        "release_key": package.release.release_key,
        "source_kind": package.release.source_kind.value,
        "is_test_fixture": package.release.is_test_fixture,
        "manifest_hash": package.manifest_hash,
        "course": {
            "slug": chapter.course.stable_slug,
            "title": chapter.course.title,
            "topic": chapter.course.topic,
        },
        "chapter": {
            "slug": chapter.spec.stable_slug,
            "title": chapter.spec.title,
            "order_index": chapter.spec.order_index,
            "revision": chapter.spec.revision,
            "stage": chapter.spec.stage.value,
            "grade_min": chapter.spec.grade_min,
            "grade_max": chapter.spec.grade_max,
            "objectives": list(chapter.spec.objectives),
            "license_code": chapter.spec.license_code.value,
            "source": chapter.spec.source.model_dump(mode="json"),
            "knowledge_points": [item.model_dump(mode="json") for item in chapter.knowledge_points],
            "blocks": [
                block.model_dump(mode="json", exclude_none=True) for block in chapter.blocks
            ],
        },
        "content_hash": chapter.content_hash,
    }
