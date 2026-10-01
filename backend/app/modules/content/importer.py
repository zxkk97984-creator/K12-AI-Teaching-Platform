"""The single idempotent curriculum importer.

Pipeline (in this order, never partially applied):

1. ``load_package`` validates every file, path, license and hash *before* any
   database write.
2. ``build_plan`` reads the current database state and classifies every row as
   CREATE or REUSE. A stable id/revision that already exists with a different
   content hash is a hard error - a revision is never overwritten.
3. ``import_package`` writes all new rows in one transaction. The database is the
   authority for what students may read.
4. Only after a successful commit does the importer refresh the immutable
   on-disk release mirror (``curriculum/releases``). The student-facing
   ``curriculum/published`` surface is written by ``materialize_published`` and
   only for revisions that are actually PUBLISHED.

Because step 4 is not part of the database transaction, a mirror failure is
reported as ``mirror_pending`` instead of pretending the import was atomic.
Re-running the importer is idempotent and finishes the mirror.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.models import (
    Chapter,
    ChapterReviewState,
    ChapterRevision,
    Course,
    KnowledgePoint,
    PublicationStatus,
    Release,
    RevisionKnowledgePoint,
)
from app.modules.content.package import (
    LoadedChapter,
    LoadedPackage,
    canonical_json,
    revision_snapshot,
)


class ContentImportError(Exception):
    """Base class for import failures that must leave the database untouched."""


class ReleaseConflict(ContentImportError):
    pass


class CourseConflict(ContentImportError):
    pass


class ChapterConflict(ContentImportError):
    pass


class KnowledgePointConflict(ContentImportError):
    pass


class RevisionHashMismatch(ContentImportError):
    pass


class ContentNotPublishable(ContentImportError):
    pass


ACTION_CREATE = "CREATE"
ACTION_REUSE = "REUSE"


@dataclass(frozen=True)
class ChapterPlan:
    chapter: LoadedChapter
    course_action: str
    chapter_action: str
    revision_action: str
    knowledge_point_actions: dict[str, str]


@dataclass(frozen=True)
class ImportPlan:
    package: LoadedPackage
    release_action: str
    chapters: tuple[ChapterPlan, ...]

    @property
    def creates_revision(self) -> bool:
        return any(item.revision_action == ACTION_CREATE for item in self.chapters)


@dataclass
class ImportResult:
    dry_run: bool
    release_key: str
    release_action: str
    manifest_hash: str
    counters: dict[str, int] = field(default_factory=dict)
    actions: list[dict[str, str]] = field(default_factory=list)
    mirrored: list[str] = field(default_factory=list)
    mirror_pending: bool = False
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "release_key": self.release_key,
            "release_action": self.release_action,
            "manifest_hash": self.manifest_hash,
            "counters": self.counters,
            "actions": self.actions,
            "mirrored": self.mirrored,
            "mirror_pending": self.mirror_pending,
            "warnings": self.warnings,
        }


async def _existing_release(db: AsyncSession, release_key: str) -> Release | None:
    return await db.scalar(select(Release).where(Release.release_key == release_key))


async def _existing_course(db: AsyncSession, slug: str) -> Course | None:
    return await db.scalar(select(Course).where(Course.stable_slug == slug))


async def _existing_chapter(db: AsyncSession, course_id: uuid.UUID, slug: str) -> Chapter | None:
    return await db.scalar(
        select(Chapter).where(Chapter.course_id == course_id, Chapter.stable_slug == slug)
    )


async def build_plan(db: AsyncSession, package: LoadedPackage) -> ImportPlan:
    release = await _existing_release(db, package.release.release_key)
    if release is not None:
        problems = []
        if release.manifest_hash != package.manifest_hash:
            problems.append("manifest_hash")
        if release.source_kind != package.release.source_kind.value:
            problems.append("source_kind")
        if release.is_test_fixture != package.release.is_test_fixture:
            problems.append("is_test_fixture")
        if release.local_demo_visible != package.release.local_demo_visible:
            problems.append("local_demo_visible")
        if problems:
            raise ReleaseConflict(
                f"release {package.release.release_key} already exists with different "
                f"{', '.join(problems)}"
            )
        release_action = ACTION_REUSE
    else:
        release_action = ACTION_CREATE

    chapter_plans: list[ChapterPlan] = []
    for item in package.chapters:
        spec = item.spec
        course = await _existing_course(db, item.course.stable_slug)
        if course is None:
            course_action = ACTION_CREATE
        else:
            if (
                course.title != item.course.title
                or course.topic != item.course.topic
                or course.description != item.course.description
            ):
                raise CourseConflict(
                    f"course {item.course.stable_slug} exists with different metadata"
                )
            course_action = ACTION_REUSE

        chapter = None
        if course is not None:
            chapter = await _existing_chapter(db, course.id, spec.stable_slug)
        if chapter is None:
            chapter_action = ACTION_CREATE
        else:
            if chapter.title != spec.title or chapter.order_index != spec.order_index:
                raise ChapterConflict(
                    f"chapter {item.course.stable_slug}/{spec.stable_slug} exists with "
                    "different title or order_index"
                )
            chapter_action = ACTION_REUSE

        revision = None
        if chapter is not None:
            revision = await db.scalar(
                select(ChapterRevision).where(
                    ChapterRevision.chapter_id == chapter.id,
                    ChapterRevision.revision == spec.revision,
                )
            )
        if revision is None:
            revision_action = ACTION_CREATE
        else:
            if revision.content_hash != item.content_hash:
                raise RevisionHashMismatch(
                    f"revision {item.course.stable_slug}/{spec.stable_slug}"
                    f"@r{spec.revision} already exists with a different content hash"
                )
            revision_action = ACTION_REUSE

        knowledge_point_actions: dict[str, str] = {}
        for knowledge_point in item.knowledge_points:
            existing = await db.scalar(
                select(KnowledgePoint).where(KnowledgePoint.stable_slug == knowledge_point.slug)
            )
            if existing is None:
                knowledge_point_actions[knowledge_point.slug] = ACTION_CREATE
            else:
                if (
                    existing.name != knowledge_point.name
                    or existing.topic != knowledge_point.topic
                    or existing.description != knowledge_point.description
                ):
                    raise KnowledgePointConflict(
                        f"knowledge point {knowledge_point.slug} exists with different metadata"
                    )
                knowledge_point_actions[knowledge_point.slug] = ACTION_REUSE

        chapter_plans.append(
            ChapterPlan(
                chapter=item,
                course_action=course_action,
                chapter_action=chapter_action,
                revision_action=revision_action,
                knowledge_point_actions=knowledge_point_actions,
            )
        )
    return ImportPlan(package=package, release_action=release_action, chapters=tuple(chapter_plans))


def _counters(plan: ImportPlan) -> dict[str, int]:
    course_actions: dict[str, str] = {}
    knowledge_point_actions: dict[str, str] = {}
    for item in plan.chapters:
        course_actions.setdefault(item.chapter.course.stable_slug, item.course_action)
        for slug, action in item.knowledge_point_actions.items():
            current = knowledge_point_actions.get(slug)
            if current is None or (current == ACTION_REUSE and action == ACTION_CREATE):
                knowledge_point_actions[slug] = action
    return {
        "courses_created": sum(1 for action in course_actions.values() if action == ACTION_CREATE),
        "courses_reused": sum(1 for action in course_actions.values() if action == ACTION_REUSE),
        "chapters_created": sum(
            1 for item in plan.chapters if item.chapter_action == ACTION_CREATE
        ),
        "chapters_reused": sum(1 for item in plan.chapters if item.chapter_action == ACTION_REUSE),
        "revisions_created": sum(
            1 for item in plan.chapters if item.revision_action == ACTION_CREATE
        ),
        "revisions_reused": sum(
            1 for item in plan.chapters if item.revision_action == ACTION_REUSE
        ),
        "knowledge_points_created": sum(
            1 for action in knowledge_point_actions.values() if action == ACTION_CREATE
        ),
        "knowledge_points_reused": sum(
            1 for action in knowledge_point_actions.values() if action == ACTION_REUSE
        ),
        "knowledge_point_links_created": sum(
            len(item.chapter.knowledge_points)
            for item in plan.chapters
            if item.revision_action == ACTION_CREATE
        ),
    }


async def _apply_plan(db: AsyncSession, plan: ImportPlan) -> None:
    package = plan.package
    release = await _existing_release(db, package.release.release_key)
    if release is None:
        release = Release(
            id=uuid.uuid4(),
            release_key=package.release.release_key,
            source_kind=package.release.source_kind.value,
            is_test_fixture=package.release.is_test_fixture,
            local_demo_visible=package.release.local_demo_visible,
            description=package.release.description,
            manifest_hash=package.manifest_hash,
        )
        db.add(release)
        await db.flush()

    for item in plan.chapters:
        spec = item.chapter.spec
        course = await _existing_course(db, item.chapter.course.stable_slug)
        if course is None:
            course = Course(
                id=uuid.uuid4(),
                stable_slug=item.chapter.course.stable_slug,
                title=item.chapter.course.title,
                topic=item.chapter.course.topic,
                description=item.chapter.course.description,
            )
            db.add(course)
            await db.flush()
        chapter = await _existing_chapter(db, course.id, spec.stable_slug)
        if chapter is None:
            chapter = Chapter(
                id=uuid.uuid4(),
                course_id=course.id,
                stable_slug=spec.stable_slug,
                order_index=spec.order_index,
                title=spec.title,
            )
            db.add(chapter)
            await db.flush()

        revision = await db.scalar(
            select(ChapterRevision).where(
                ChapterRevision.chapter_id == chapter.id,
                ChapterRevision.revision == spec.revision,
            )
        )
        if revision is None:
            revision = ChapterRevision(
                id=uuid.uuid4(),
                release_id=release.id,
                chapter_id=chapter.id,
                revision=spec.revision,
                stage=spec.stage.value,
                grade_min=spec.grade_min,
                grade_max=spec.grade_max,
                objectives=list(spec.objectives),
                body=[
                    block.model_dump(mode="json", exclude_none=True)
                    for block in item.chapter.blocks
                ],
                content_hash=item.chapter.content_hash,
                source_manifest={
                    "source_commit": spec.source.source_commit,
                    "source_path": spec.source.source_path,
                    "original_sha256": spec.source.original_sha256,
                    "conversion": spec.source.conversion,
                    "release_key": package.release.release_key,
                    "license_code": spec.license_code.value,
                    "license_notes": spec.license_notes,
                    "source_kind": package.release.source_kind.value,
                },
                license_code=spec.license_code.value,
            )
            db.add(revision)
            await db.flush()
            db.add(
                ChapterReviewState(
                    revision_id=revision.id,
                    review_status="UNREVIEWED",
                    publication_status=PublicationStatus.DRAFT.value,
                )
            )

        for position, knowledge_point in enumerate(item.chapter.knowledge_points):
            row = await db.scalar(
                select(KnowledgePoint).where(KnowledgePoint.stable_slug == knowledge_point.slug)
            )
            if row is None:
                row = KnowledgePoint(
                    id=uuid.uuid4(),
                    stable_slug=knowledge_point.slug,
                    name=knowledge_point.name,
                    topic=knowledge_point.topic,
                    description=knowledge_point.description,
                )
                db.add(row)
                await db.flush()
            link = await db.scalar(
                select(RevisionKnowledgePoint).where(
                    RevisionKnowledgePoint.revision_id == revision.id,
                    RevisionKnowledgePoint.knowledge_point_id == row.id,
                )
            )
            if link is None:
                db.add(
                    RevisionKnowledgePoint(
                        revision_id=revision.id,
                        knowledge_point_id=row.id,
                        position=position,
                    )
                )
    await db.flush()


def _write_atomic(path: Path, text: str) -> str:
    """Write a file atomically; identical existing content is reused."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return ACTION_REUSE
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
    return ACTION_CREATE


def mirror_revision(mirror_root: Path, package: LoadedPackage, chapter: LoadedChapter) -> str:
    snapshot = revision_snapshot(package, chapter)
    path = (
        mirror_root
        / package.release.release_key
        / chapter.course.stable_slug
        / f"{chapter.spec.stable_slug}-r{chapter.spec.revision}.json"
    )
    return _write_atomic(path, canonical_json(snapshot) + "\n")


def materialize_published(
    published_root: Path,
    package: LoadedPackage,
    chapter: LoadedChapter,
    review_state: ChapterReviewState,
) -> str:
    """Write the student-visible snapshot. Only PUBLISHED revisions may land here."""

    if review_state.publication_status != PublicationStatus.PUBLISHED.value:
        raise ContentNotPublishable(
            f"revision {chapter.spec.stable_slug}@r{chapter.spec.revision} is "
            f"{review_state.publication_status}, not PUBLISHED"
        )
    snapshot = revision_snapshot(package, chapter)
    snapshot["publication"] = {
        "published_by": review_state.published_by,
        "published_at": review_state.published_at.isoformat()
        if isinstance(review_state.published_at, datetime)
        else None,
        "reviewer": review_state.reviewer,
    }
    path = (
        published_root
        / chapter.course.stable_slug
        / f"{chapter.spec.stable_slug}-r{chapter.spec.revision}.json"
    )
    return _write_atomic(path, canonical_json(snapshot) + "\n")


async def import_package(
    db: AsyncSession,
    package: LoadedPackage,
    *,
    dry_run: bool = True,
    mirror_root: Path | None = None,
) -> ImportResult:
    plan = await build_plan(db, package)
    result = ImportResult(
        dry_run=dry_run,
        release_key=package.release.release_key,
        release_action=plan.release_action,
        manifest_hash=package.manifest_hash,
        counters=_counters(plan),
        actions=[
            {
                "course": item.chapter.course.stable_slug,
                "chapter": item.chapter.spec.stable_slug,
                "revision": str(item.chapter.spec.revision),
                "course_action": item.course_action,
                "chapter_action": item.chapter_action,
                "revision_action": item.revision_action,
                "content_hash": item.chapter.content_hash,
            }
            for item in plan.chapters
        ],
    )
    if dry_run:
        await db.rollback()
        return result

    await _apply_plan(db, plan)
    await db.commit()

    if mirror_root is not None:
        for item in plan.chapters:
            try:
                action = mirror_revision(mirror_root, package, item.chapter)
            except OSError as exc:  # pragma: no cover - disk failure path
                result.mirror_pending = True
                result.warnings.append(f"mirror failed for {item.chapter.spec.stable_slug}: {exc}")
                continue
            result.mirrored.append(f"{item.chapter.spec.stable_slug}:{action}")
    return result
