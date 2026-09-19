"""Review/publication transitions and student visibility rules for content.

Two facts are deliberately separate:

* Technical validation may produce ``AUTO_VALIDATED``. It never produces a
  reviewer identity and it never publishes.
* Only a real reviewer identity may produce ``HUMAN_APPROVED``; only a
  human-approved, non-fixture revision may become ``PUBLISHED``.

``ContentProfile`` decides which surface a runtime exposes. Production runs the
``formal`` profile: human approved, published, non-fixture revisions inside the
student's stage and (when set) grade range. Development/test additionally expose
synthetic fixtures so the teaching flow can be built before human review, and
always mark them as test content. Non-fixture drafts are never student visible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.content.models import (
    Chapter,
    ChapterReviewState,
    ChapterRevision,
    ContentProfile,
    Course,
    KnowledgePoint,
    LicenseCode,
    PublicationStatus,
    ReadingEvent,
    ReadingEventKind,
    Release,
    ReviewStatus,
    RevisionKnowledgePoint,
    SourceKind,
)
from app.modules.content.schemas import (
    ChapterDetailDTO,
    ChapterNavigationDTO,
    ChapterSummaryDTO,
    CourseSummaryDTO,
    KnowledgePointDTO,
    NeighborRefDTO,
    PageContextDTO,
    PageContextRequest,
    ReadingEventReceipt,
    ReadingEventRequest,
    ReadingStateDTO,
    RenderedBlock,
    SourceRefDTO,
    UnknownBlockDTO,
    ViewerScope,
)
from app.modules.identity.models import LearnerProfile

FIXTURE_NOTICE = "测试内容，未作人工教学审校"
AUTO_VALIDATION_ACTOR = "auto-validation"

REVIEWABLE_STATUSES = {ReviewStatus.AUTO_VALIDATED, ReviewStatus.HUMAN_APPROVED}


class ContentReviewError(Exception):
    """A review transition that the domain rules refuse."""


def content_profile_for(settings: Settings) -> ContentProfile:
    """Production serves formal content only; dev/test may load fixtures."""

    return ContentProfile.FORMAL if settings.app_env == "production" else ContentProfile.DEVELOPMENT


def viewer_scope_from_profile(profile: LearnerProfile | None, settings: Settings) -> ViewerScope:
    return ViewerScope(
        stage=profile.stage if profile is not None else None,
        grade=profile.grade if profile is not None else None,
        profile=content_profile_for(settings),
    )


def _notice(is_test_fixture: bool) -> str | None:
    return FIXTURE_NOTICE if is_test_fixture else None


def _summary(
    revision: ChapterRevision,
    chapter: Chapter,
    course: Course,
    release: Release,
    review_state: ChapterReviewState,
) -> ChapterSummaryDTO:
    return ChapterSummaryDTO(
        chapter_id=chapter.id,
        course_id=course.id,
        course_slug=course.stable_slug,
        course_title=course.title,
        chapter_slug=chapter.stable_slug,
        title=chapter.title,
        order_index=chapter.order_index,
        stage=revision.stage,
        grade_min=revision.grade_min,
        grade_max=revision.grade_max,
        revision=revision.revision,
        revision_id=revision.id,
        source_kind=SourceKind(release.source_kind),
        publication_status=PublicationStatus(review_state.publication_status),
        review_status=ReviewStatus(review_state.review_status),
        is_test_fixture=release.is_test_fixture,
        content_notice=_notice(release.is_test_fixture),
    )


def visibility_conditions(viewer: ViewerScope):
    """Return the SQL predicate for one viewer, or None when nothing may be read."""

    if viewer.stage is None:
        return None
    stage = viewer.stage.value
    published = and_(
        ChapterRevision.stage == stage,
        Release.is_test_fixture.is_(False),
        ChapterReviewState.review_status == ReviewStatus.HUMAN_APPROVED.value,
        ChapterReviewState.publication_status == PublicationStatus.PUBLISHED.value,
    )
    alternatives = [published]
    if viewer.profile is ContentProfile.DEVELOPMENT:
        # Synthetic fixtures are explicit test content: no approval exists yet,
        # they are always labelled in the response, and they can never be
        # PUBLISHED (database trigger). Withdrawn fixtures stay hidden.
        alternatives.append(
            and_(
                ChapterRevision.stage == stage,
                Release.is_test_fixture.is_(True),
                ChapterReviewState.publication_status != PublicationStatus.WITHDRAWN.value,
            )
        )
    condition = or_(*alternatives)
    if viewer.grade is not None:
        condition = and_(
            condition,
            or_(
                and_(ChapterRevision.grade_min.is_(None), ChapterRevision.grade_max.is_(None)),
                and_(
                    ChapterRevision.grade_min <= viewer.grade,
                    ChapterRevision.grade_max >= viewer.grade,
                ),
            ),
        )
    return condition


async def visible_chapters(db: AsyncSession, viewer: ViewerScope) -> list[ChapterSummaryDTO]:
    condition = visibility_conditions(viewer)
    if condition is None:
        return []
    statement = (
        select(ChapterRevision, Chapter, Course, Release, ChapterReviewState)
        .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .join(Release, Release.id == ChapterRevision.release_id)
        .join(ChapterReviewState, ChapterReviewState.revision_id == ChapterRevision.id)
        .where(condition)
        .distinct(ChapterRevision.chapter_id)
        .order_by(ChapterRevision.chapter_id, ChapterRevision.revision.desc())
    )
    rows = (await db.execute(statement)).all()
    summaries = [_summary(*row) for row in rows]
    summaries.sort(key=lambda item: (item.course_slug, item.order_index, item.chapter_slug))
    return summaries


async def visible_courses(db: AsyncSession, viewer: ViewerScope) -> list[CourseSummaryDTO]:
    """Courses that currently have at least one chapter the viewer may read."""

    chapters = await visible_chapters(db, viewer)
    grouped: dict[uuid.UUID, list[ChapterSummaryDTO]] = {}
    for chapter in chapters:
        grouped.setdefault(chapter.course_id, []).append(chapter)
    if not grouped:
        return []
    rows = (await db.execute(select(Course).where(Course.id.in_(list(grouped))))).scalars()
    courses = {
        course.id: CourseSummaryDTO(
            course_id=course.id,
            slug=course.stable_slug,
            title=course.title,
            topic=course.topic,
            description=course.description,
            chapters=grouped[course.id],
        )
        for course in rows
    }
    return sorted(courses.values(), key=lambda item: item.slug)


async def visible_course(
    db: AsyncSession, *, course_id: uuid.UUID, viewer: ViewerScope
) -> CourseSummaryDTO | None:
    chapters = [
        chapter for chapter in await visible_chapters(db, viewer) if chapter.course_id == course_id
    ]
    if not chapters:
        return None
    course = await db.scalar(select(Course).where(Course.id == course_id))
    if course is None:  # pragma: no cover - FK guarantees the row
        return None
    return CourseSummaryDTO(
        course_id=course.id,
        slug=course.stable_slug,
        title=course.title,
        topic=course.topic,
        description=course.description,
        chapters=chapters,
    )


def render_blocks(body: list[dict]) -> list[RenderedBlock | UnknownBlockDTO]:
    """Attach stable per-revision block ids.

    A block that no longer validates (for example a row edited outside the
    importer) becomes an explicit UNSUPPORTED placeholder at the same position:
    it is never silently dropped and its raw payload is never rendered.
    """

    blocks: list[RenderedBlock | UnknownBlockDTO] = []
    for index, raw in enumerate(body, start=1):
        block_id = f"b{index}"
        try:
            blocks.append(RenderedBlock(**{**raw, "block_id": block_id}))
        except Exception:
            blocks.append(
                UnknownBlockDTO(
                    block_id=block_id,
                    reason="内容块未通过服务端校验，已保留位置但不渲染原始内容。",
                )
            )
    return blocks


def _section_keys(body: list[dict]) -> set[str]:
    return {
        str(block.get("key"))
        for block in body
        if block.get("type") == "SECTION" and block.get("key")
    }


def _block_ids(body: list[dict]) -> set[str]:
    return {f"b{index}" for index in range(1, len(body) + 1)}


def valid_locator(body: list[dict], *, section_key: str | None, block_id: str | None) -> bool:
    if section_key is not None and section_key not in _section_keys(body):
        return False
    if block_id is not None and block_id not in _block_ids(body):
        return False
    return True


async def _chapter_navigation(
    db: AsyncSession, *, chapter: Chapter, viewer: ViewerScope
) -> ChapterNavigationDTO:
    siblings = [
        item for item in await visible_chapters(db, viewer) if item.course_id == chapter.course_id
    ]
    siblings.sort(key=lambda item: (item.order_index, item.chapter_slug))
    index = next(
        (position for position, item in enumerate(siblings) if item.chapter_id == chapter.id),
        None,
    )
    if index is None:
        return ChapterNavigationDTO(prev=None, next=None)

    def ref(item: ChapterSummaryDTO) -> NeighborRefDTO:
        return NeighborRefDTO(
            chapter_id=item.chapter_id,
            slug=item.chapter_slug,
            title=item.title,
            revision=item.revision,
        )

    return ChapterNavigationDTO(
        prev=ref(siblings[index - 1]) if index > 0 else None,
        next=ref(siblings[index + 1]) if index + 1 < len(siblings) else None,
    )


async def visible_chapter_detail(
    db: AsyncSession,
    *,
    chapter_id: uuid.UUID,
    viewer: ViewerScope,
    revision: int | None = None,
) -> ChapterDetailDTO | None:
    condition = visibility_conditions(viewer)
    if condition is None:
        return None
    statement = (
        select(ChapterRevision, Chapter, Course, Release, ChapterReviewState)
        .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .join(Release, Release.id == ChapterRevision.release_id)
        .join(ChapterReviewState, ChapterReviewState.revision_id == ChapterRevision.id)
        .where(
            ChapterRevision.chapter_id == chapter_id,
            condition,
            *([ChapterRevision.revision == revision] if revision is not None else []),
        )
        .order_by(ChapterRevision.revision.desc())
        .limit(1)
    )
    row = (await db.execute(statement)).first()
    if row is None:
        return None
    revision_row, chapter, course, release, review_state = row
    manifest = dict(revision_row.source_manifest)
    knowledge_points = (
        await db.execute(
            select(KnowledgePoint)
            .join(
                RevisionKnowledgePoint,
                RevisionKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
            )
            .where(RevisionKnowledgePoint.revision_id == revision_row.id)
            .order_by(RevisionKnowledgePoint.position)
        )
    ).scalars()
    summary = _summary(revision_row, chapter, course, release, review_state)
    return ChapterDetailDTO(
        **summary.model_dump(),
        objectives=list(revision_row.objectives),
        knowledge_points=[
            KnowledgePointDTO(
                slug=item.stable_slug,
                name=item.name,
                topic=item.topic,
                description=item.description,
            )
            for item in knowledge_points
        ],
        blocks=render_blocks(list(revision_row.body)),
        source=SourceRefDTO(
            source_kind=manifest.get("source_kind") or release.source_kind,
            source_commit=manifest.get("source_commit"),
            source_path=manifest.get("source_path"),
            conversion=manifest.get("conversion"),
            license_code=LicenseCode(revision_row.license_code),
        ),
        license_code=LicenseCode(revision_row.license_code),
        navigation=await _chapter_navigation(db, chapter=chapter, viewer=viewer),
    )


async def _visible_revision_row(
    db: AsyncSession,
    *,
    chapter_id: uuid.UUID,
    viewer: ViewerScope,
    revision: int | None = None,
) -> ChapterRevision | None:
    condition = visibility_conditions(viewer)
    if condition is None:
        return None
    statement = (
        select(ChapterRevision)
        .join(Release, Release.id == ChapterRevision.release_id)
        .join(ChapterReviewState, ChapterReviewState.revision_id == ChapterRevision.id)
        .where(
            ChapterRevision.chapter_id == chapter_id,
            condition,
            *([ChapterRevision.revision == revision] if revision is not None else []),
        )
        .order_by(ChapterRevision.revision.desc())
        .limit(1)
    )
    return await db.scalar(statement)


def normalize_selected_text(value: str) -> str:
    return " ".join(value.split())


def _authoritative_text(body: list[dict], block_id: str | None, section_key: str | None) -> str:
    if block_id is not None:
        index = int(block_id[1:]) - 1
        if 0 <= index < len(body):
            block = body[index]
            parts = [block.get("text"), block.get("title"), block.get("caption"), block.get("alt")]
            return " ".join(str(part) for part in parts if part)
    if section_key is not None:
        for block in body:
            if block.get("type") == "SECTION" and block.get("key") == section_key:
                return str(block.get("text") or "")
    return whole_chapter_text(body)


def whole_chapter_text(body: list[dict]) -> str:
    """Normalized text of the whole immutable revision (cross-block selections)."""

    parts: list[str] = []
    for block in body:
        for key in ("text", "title", "caption", "alt"):
            value = block.get(key)
            if value:
                parts.append(str(value))
    return " ".join(parts)


class ContentNotVisible(Exception):
    """The requested chapter revision is not readable by this viewer."""


class InvalidContext(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def resolve_page_context(
    db: AsyncSession, *, viewer: ViewerScope, payload: PageContextRequest
) -> PageContextDTO:
    revision_row = await _visible_revision_row(
        db, chapter_id=payload.chapter_id, viewer=viewer, revision=payload.revision
    )
    if revision_row is None:
        raise ContentNotVisible("chapter revision is not readable")
    body = list(revision_row.body)
    if not valid_locator(body, section_key=payload.section_key, block_id=payload.block_id):
        raise InvalidContext("LOCATOR_UNKNOWN", "章节中不存在该小节或内容块")
    selected: str | None = None
    if payload.selected_text is not None:
        selected = normalize_selected_text(payload.selected_text)
        if not selected:
            raise InvalidContext("SELECTION_EMPTY", "选中文字为空")
        if len(selected) > 500:
            raise InvalidContext("SELECTION_TOO_LONG", "选中文字超过 500 字上限")
        if selected not in _authoritative_text(
            body, payload.block_id, payload.section_key
        ) and selected not in whole_chapter_text(body):
            raise InvalidContext("SELECTION_NOT_IN_SOURCE", "选中文字与权威正文不一致")
    return PageContextDTO(
        chapter_id=payload.chapter_id,
        revision=revision_row.revision,
        source_id=f"chapter:{payload.chapter_id}",
        section_key=payload.section_key,
        block_id=payload.block_id,
        selected_text=selected,
        selected_text_chars=len(selected) if selected else 0,
        generated_at=datetime.now(UTC),
    )


async def record_reading_event(
    db: AsyncSession, *, viewer: ViewerScope, user_id: uuid.UUID, payload: ReadingEventRequest
) -> ReadingEventReceipt:
    revision_row = await _visible_revision_row(
        db, chapter_id=payload.chapter_id, viewer=viewer, revision=payload.revision
    )
    if revision_row is None:
        raise ContentNotVisible("chapter revision is not readable")
    body = list(revision_row.body)
    if not valid_locator(body, section_key=payload.section_key, block_id=payload.block_id):
        raise InvalidContext("LOCATOR_UNKNOWN", "章节中不存在该小节或内容块")

    existing = await db.scalar(
        select(ReadingEvent).where(
            ReadingEvent.user_id == user_id,
            ReadingEvent.client_event_id == payload.client_event_id,
        )
    )
    if existing is not None:
        return ReadingEventReceipt(
            event_id=existing.id, duplicate=True, recorded_at=existing.created_at
        )

    recorded_at = datetime.now(UTC)
    event = ReadingEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        chapter_id=payload.chapter_id,
        revision_id=revision_row.id,
        client_event_id=payload.client_event_id,
        event_kind=payload.event_kind.value,
        section_key=payload.section_key,
        block_id=payload.block_id,
        selected_text_length=payload.selected_text_length,
        created_at=recorded_at,
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(ReadingEvent).where(
                ReadingEvent.user_id == user_id,
                ReadingEvent.client_event_id == payload.client_event_id,
            )
        )
        if existing is None:  # pragma: no cover - unexpected constraint failure
            raise
        return ReadingEventReceipt(
            event_id=existing.id, duplicate=True, recorded_at=existing.created_at
        )
    return ReadingEventReceipt(event_id=event.id, duplicate=False, recorded_at=recorded_at)


async def latest_reading_state(
    db: AsyncSession, *, viewer: ViewerScope, user_id: uuid.UUID, chapter_id: uuid.UUID
) -> ReadingStateDTO | None:
    current = await _visible_revision_row(db, chapter_id=chapter_id, viewer=viewer)
    if current is None:
        raise ContentNotVisible("chapter is not readable")
    event = await db.scalar(
        select(ReadingEvent)
        .where(ReadingEvent.user_id == user_id, ReadingEvent.chapter_id == chapter_id)
        .order_by(ReadingEvent.created_at.desc(), ReadingEvent.id.desc())
        .limit(1)
    )
    if event is None:
        return None
    recorded_revision = await db.scalar(
        select(ChapterRevision).where(ChapterRevision.id == event.revision_id)
    )
    if recorded_revision is None:  # pragma: no cover - FK guarantees the row
        return None
    return ReadingStateDTO(
        chapter_id=chapter_id,
        revision=recorded_revision.revision,
        revision_id=recorded_revision.id,
        event_kind=ReadingEventKind(event.event_kind),
        section_key=event.section_key,
        block_id=event.block_id,
        created_at=event.created_at,
        is_current_revision=recorded_revision.id == current.id,
    )


async def _load_revision(db: AsyncSession, revision_id: uuid.UUID) -> ChapterRevision:
    revision = await db.scalar(select(ChapterRevision).where(ChapterRevision.id == revision_id))
    if revision is None:
        raise ContentReviewError("unknown chapter revision")
    return revision


async def _load_state(db: AsyncSession, revision_id: uuid.UUID) -> ChapterReviewState:
    state = await db.scalar(
        select(ChapterReviewState).where(ChapterReviewState.revision_id == revision_id)
    )
    if state is None:
        raise ContentReviewError("chapter revision has no review state")
    return state


async def record_review(
    db: AsyncSession,
    *,
    revision_id: uuid.UUID,
    status: ReviewStatus,
    reviewer: str | None = None,
    comment: str | None = None,
    now: datetime | None = None,
) -> ChapterReviewState:
    """Record a technical or human review result. Never publishes content."""

    if status not in REVIEWABLE_STATUSES:
        raise ContentReviewError("review status must be AUTO_VALIDATED or HUMAN_APPROVED")
    await _load_revision(db, revision_id)
    state = await _load_state(db, revision_id)
    if state.publication_status == PublicationStatus.PUBLISHED.value and status is not (
        ReviewStatus.HUMAN_APPROVED
    ):
        raise ContentReviewError("published content cannot lose its human approval")
    timestamp = now or datetime.now(UTC)
    if status is ReviewStatus.AUTO_VALIDATED:
        state.review_status = status.value
        state.reviewer = None
        state.reviewed_at = None
    else:
        cleaned = (reviewer or "").strip()
        if len(cleaned) < 2:
            raise ContentReviewError("human approval requires a reviewer identity")
        state.review_status = status.value
        state.reviewer = cleaned
        state.reviewed_at = timestamp
    if comment is not None:
        state.review_comment = comment.strip() or None
    await db.commit()
    return state


async def publish_revision(
    db: AsyncSession,
    *,
    revision_id: uuid.UUID,
    actor: str,
    now: datetime | None = None,
) -> ChapterReviewState:
    """Publish a human-approved, non-fixture revision."""

    cleaned_actor = (actor or "").strip()
    if len(cleaned_actor) < 2:
        raise ContentReviewError("publishing requires an actor identity")
    revision = await _load_revision(db, revision_id)
    state = await _load_state(db, revision_id)
    release = await db.scalar(select(Release).where(Release.id == revision.release_id))
    if release is None:  # pragma: no cover - FK guarantees the row
        raise ContentReviewError("chapter revision has no release")
    if state.review_status != ReviewStatus.HUMAN_APPROVED.value:
        raise ContentReviewError("only human approved revisions can be published")
    if release.is_test_fixture or revision.license_code == LicenseCode.SYNTHETIC_FIXTURE.value:
        raise ContentReviewError("synthetic fixture content cannot be published")
    state.publication_status = PublicationStatus.PUBLISHED.value
    state.published_by = cleaned_actor
    state.published_at = now or datetime.now(UTC)
    await db.commit()
    return state


async def withdraw_revision(
    db: AsyncSession,
    *,
    revision_id: uuid.UUID,
    actor: str,
    comment: str | None = None,
    now: datetime | None = None,
) -> ChapterReviewState:
    cleaned_actor = (actor or "").strip()
    if len(cleaned_actor) < 2:
        raise ContentReviewError("withdrawing requires an actor identity")
    await _load_revision(db, revision_id)
    state = await _load_state(db, revision_id)
    state.publication_status = PublicationStatus.WITHDRAWN.value
    state.withdrawn_by = cleaned_actor
    state.withdrawn_at = now or datetime.now(UTC)
    if comment is not None:
        state.review_comment = comment.strip() or None
    await db.commit()
    return state
