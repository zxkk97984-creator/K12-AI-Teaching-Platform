from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.assessment.models import QuizAttempt, QuizQuestion, QuizSession
from app.modules.codelab.models import CodeRun, CodeTaskRevision
from app.modules.content.models import (
    Chapter,
    ChapterRevision,
    Course,
    KnowledgePoint,
    ReadingEvent,
    RevisionKnowledgePoint,
)
from app.modules.content.service import (
    viewer_scope_from_profile,
    visible_chapter_detail,
    visible_chapters,
)
from app.modules.identity.models import LearnerProfile
from app.modules.interactive.models import InteractiveSession
from app.modules.learning.models import PicturebookProgress
from app.modules.learning.study_content import visible_picturebooks
from app.modules.learning.study_router import (
    _open_history_rows,
    _resolve_visible_target,
)
from app.modules.lookup.schemas import (
    LookupCard,
    LookupInput,
    LookupResult,
    LookupTarget,
    SourceRef,
)
from app.modules.resources.models import Resource, ResourceKnowledgePoint
from app.modules.resources.service import visibility_condition
from app.modules.teaching.models import LessonSession

SHANGHAI = ZoneInfo("Asia/Shanghai")
LABELS = {
    "COURSE_SEARCH": "课程与资料",
    "WRONG_QUESTIONS": "本人错题",
    "LEARNING_PROGRESS": "学习进度",
}


@dataclass(frozen=True)
class LookupRuntime:
    """Never serialized into model input or accepted from model parameters."""

    db: AsyncSession
    owner_user_id: uuid.UUID
    expected_stage: str
    settings: Settings


def date_bounds(params: LookupInput, now: datetime):
    def parse(value: str | None, end: bool):
        if value is None:
            return None
        day = now.astimezone(SHANGHAI).date()
        if value == "昨天":
            day -= timedelta(days=1)
        elif value != "今天":
            day = datetime.fromisoformat(value).date()
        return datetime.combine(day + timedelta(days=int(end)), time.min, SHANGHAI)

    since, until = parse(params.since, False), parse(params.until, True)
    if since and until and since >= until:
        raise ValueError("invalid date range")
    return since, until


def _time_filter(column, bounds):
    since, until = bounds
    return [*([column >= since] if since else []), *([column < until] if until else [])]


def _matches(params: LookupInput, *values: str):
    searchable = " ".join(value or "" for value in values).casefold()
    return all(
        not value.strip() or value.strip().casefold() in searchable
        for value in (params.keyword, params.topic)
    )


def _card(
    tool,
    kind,
    identifier,
    title,
    description,
    now,
    *,
    target=None,
    route=None,
    revision="1",
    recorded_at=None,
    explanation=None,
    notice=None,
):
    return LookupCard(
        id=f"lookup:{identifier}",
        tool=tool,
        kind=kind,
        status="OK",
        title=title[:250],
        description=description[:180] + ("…" if len(description) > 180 else ""),
        queried_at=now.isoformat(),
        target=target,
        route=route,
        source_ref=SourceRef(
            source_id=f"lookup:{identifier}", revision=str(revision), locator=title[:300]
        ),
        recorded_at=recorded_at.isoformat() if recorded_at else None,
        explanation=explanation[:600] if explanation else None,
        content_notice=notice[:200] if notice else None,
    )


def result_for(tool, cards, params, now, *, capped=False):
    total = len(cards)
    summary = (
        f"找到 {total}{' 条以上' if capped else ' 条'}记录，显示前 {params.limit} 条。"
        if cards
        else "没有符合条件的记录。"
    )
    if not cards and capped:
        summary = "近期可用记录中没有匹配项；更早的记录未包含在这次查询中。"
    return LookupResult(
        tool=tool,
        status="OK" if cards else "EMPTY",
        queried_at=now.isoformat(),
        summary=summary,
        cards=cards[: params.limit],
        total=None if capped else total,
        truncated=capped or total > params.limit,
    )


async def _viewer(runtime):
    profile = await runtime.db.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == runtime.owner_user_id)
    )
    if profile is None or not profile.stage or profile.stage != runtime.expected_stage:
        raise ValueError("viewer unavailable or changed")
    return viewer_scope_from_profile(profile, runtime.settings)


async def course_search(params: LookupInput, context: dict, *, runtime: LookupRuntime):
    del context
    db, now = runtime.db, datetime.now(UTC)
    viewer = await _viewer(runtime)
    cards = []
    if params.content_type in (None, "COURSE"):
        for chapter in await visible_chapters(db, viewer):
            course = await db.get(Course, chapter.course_id)
            points = list(
                await db.scalars(
                    select(KnowledgePoint.name)
                    .join(RevisionKnowledgePoint)
                    .where(RevisionKnowledgePoint.revision_id == chapter.revision_id)
                )
            )
            if not _matches(
                params, chapter.title, course.title, course.topic, course.description, *points
            ):
                continue
            cards.append(
                _card(
                    "COURSE_SEARCH",
                    "COURSE",
                    f"chapter:{chapter.revision_id}",
                    chapter.title,
                    f"{course.title} · {course.description}",
                    now,
                    target=LookupTarget(
                        type="CHAPTER", id=str(chapter.chapter_id), revision=str(chapter.revision)
                    ),
                    route=f"/chapters/{chapter.chapter_id}?revision={chapter.revision}",
                    revision=chapter.revision,
                    notice=chapter.content_notice,
                )
            )
    if params.content_type in (None, "RESOURCE"):
        filters = [visibility_condition(viewer)]
        for value in (params.keyword.strip(), params.topic.strip()):
            if value:
                point = (
                    select(ResourceKnowledgePoint.resource_id)
                    .join(KnowledgePoint)
                    .where(
                        or_(
                            KnowledgePoint.name.icontains(value, autoescape=True),
                            KnowledgePoint.stable_slug.icontains(value, autoescape=True),
                            KnowledgePoint.topic.icontains(value, autoescape=True),
                        )
                    )
                )
                filters.append(
                    or_(
                        Resource.title.icontains(value, autoescape=True),
                        Resource.description.icontains(value, autoescape=True),
                        Resource.id.in_(point),
                    )
                )
        resources = list(await db.scalars(select(Resource).where(*filters).order_by(Resource.id)))
        for resource in resources:
            target = await _resolve_visible_target(
                db,
                viewer=viewer,
                kind="RESOURCE",
                target_id=str(resource.id),
                settings=runtime.settings,
                require_file=False,
            )
            if not target:
                continue
            card = _card(
                "COURSE_SEARCH",
                "RESOURCE",
                f"resource:{resource.id}",
                resource.title,
                resource.description,
                now,
                target=LookupTarget(
                    type="RESOURCE", id=str(resource.id), revision=target.get("target_version")
                ),
                route=target["route"],
                revision=target.get("target_version") or "1",
                notice=target.get("content_notice"),
            )
            if not target.get("available", True):
                card.status, card.target, card.route = "UNAVAILABLE", None, None
                card.description = "资料文件暂不可用。"
            cards.append(card)
    return result_for("COURSE_SEARCH", cards, params, now)


async def wrong_questions(params: LookupInput, context: dict, *, runtime: LookupRuntime):
    del context
    db, now = runtime.db, datetime.now(UTC)
    await _viewer(runtime)
    query = (
        select(QuizAttempt, QuizQuestion, QuizSession, Course.topic)
        .join(QuizQuestion, QuizQuestion.id == QuizAttempt.question_id)
        .join(QuizSession, QuizSession.id == QuizAttempt.session_id)
        .outerjoin(Chapter, Chapter.id == QuizSession.chapter_id)
        .outerjoin(Course, Course.id == Chapter.course_id)
        .where(
            QuizAttempt.owner_user_id == runtime.owner_user_id,
            QuizSession.owner_user_id == runtime.owner_user_id,
            QuizQuestion.session_id == QuizSession.id,
            QuizSession.stage == runtime.expected_stage,
            QuizAttempt.outcome == "INCORRECT",
            QuizAttempt.is_correct.is_(False),
            QuizAttempt.attempt_no.is_not(None),
            *_time_filter(QuizAttempt.created_at, date_bounds(params, now)),
        )
        .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc())
    )
    cards, seen = [], set()
    for attempt, question, quiz, topic in (await db.execute(query)).all():
        if question.id in seen or not _matches(
            params,
            question.stem,
            quiz.source_title,
            topic or "综合",
            *list(quiz.knowledge_point_slugs or []),
        ):
            continue
        seen.add(question.id)
        # Only this scored question's released explanation, never its answer key,
        # code snapshot, hidden tests, unreleased hints or other questions.
        cards.append(
            _card(
                "WRONG_QUESTIONS",
                "WRONG_QUESTION",
                f"wrong:{question.id}",
                question.stem[:200],
                f"{quiz.source_title or '随堂练习'} · 第 {question.position + 1} 题",
                now,
                target=LookupTarget(type="QUIZ", id=str(quiz.id)),
                route=f"/practice/sessions/{quiz.id}",
                recorded_at=attempt.created_at,
                explanation=question.explanation if question.type != "CODE" else None,
            )
        )
    return result_for("WRONG_QUESTIONS", cards, params, now)


async def learning_progress(params: LookupInput, context: dict, *, runtime: LookupRuntime):
    del context
    db, now = runtime.db, datetime.now(UTC)
    viewer, bounds = await _viewer(runtime), date_bounds(params, now)
    cards, capped = [], False
    if params.content_type in (None, "READING"):
        books = {book["id"]: book for book in visible_picturebooks(runtime.expected_stage)}
        for progress in await db.scalars(
            select(PicturebookProgress).where(
                PicturebookProgress.owner_user_id == runtime.owner_user_id,
                *_time_filter(PicturebookProgress.updated_at, bounds),
            )
        ):
            book = books.get(progress.story_id)
            if book and _matches(params, book["title"], book.get("topic", "")):
                cards.append(
                    _card(
                        "LEARNING_PROGRESS",
                        "PROGRESS",
                        f"picturebook:{progress.story_id}",
                        book["title"],
                        f"阅读记录：最近查看第 {progress.page_index + 1} 页，不代表读完。",
                        now,
                        target=LookupTarget(
                            type="PICTUREBOOK", id=progress.story_id, revision=book["version"]
                        ),
                        route=f"/picturebooks/{progress.story_id}",
                        revision=book["version"],
                        recorded_at=progress.updated_at,
                        notice="合成绘本阅读示例",
                    )
                )
        # Apply the activity window before grouping: today's read must not hide
        # a read of the same chapter yesterday. Keep the most recent event in it.
        reading_rows = (
            await db.execute(
                select(ReadingEvent, ChapterRevision.revision)
                .join(ChapterRevision, ChapterRevision.id == ReadingEvent.revision_id)
                .where(
                    ReadingEvent.user_id == runtime.owner_user_id,
                    *_time_filter(ReadingEvent.created_at, bounds),
                )
                .order_by(ReadingEvent.created_at.desc(), ReadingEvent.id.desc())
                .limit(501)
            )
        ).all()
        capped = len(reading_rows) > 500
        seen_chapters = set()
        for event, revision in reading_rows[:500]:
            if event.chapter_id in seen_chapters:
                continue
            seen_chapters.add(event.chapter_id)
            detail = await visible_chapter_detail(
                db, chapter_id=event.chapter_id, revision=revision, viewer=viewer
            )
            if not detail:
                continue
            description = f"{detail.course_title} · {detail.title}"
            if _matches(params, detail.title, description):
                cards.append(
                    _card(
                        "LEARNING_PROGRESS",
                        "PROGRESS",
                        f"reading:{event.chapter_id}",
                        detail.title,
                        f"阅读过 · {description}。阅读记录不代表读完或掌握。",
                        now,
                        target=LookupTarget(
                            type="CHAPTER", id=str(event.chapter_id), revision=str(revision)
                        ),
                        route=f"/chapters/{event.chapter_id}?revision={revision}",
                        revision=revision,
                        recorded_at=event.created_at,
                    )
                )
    models = {
        "LESSON": (LessonSession, LessonSession.updated_at),
        "WATCHING": (InteractiveSession, InteractiveSession.updated_at),
        "QUIZ": (QuizSession, QuizSession.created_at),
        "CODE": (CodeRun, CodeRun.created_at),
    }
    if params.content_type in (None, "WATCHING"):
        seen = set()
        opened = await _open_history_rows(
            db, owner_user_id=runtime.owner_user_id, viewer=viewer, settings=runtime.settings
        )
        capped = capped or len(opened) >= 500
        for opened_row in opened:
            if not opened_row.available or opened_row.target_kind not in ("RESOURCE", "ANIMATION"):
                continue
            if (opened_row.target_kind, opened_row.target_id) in seen:
                continue
            if any(bounds) and not (
                (not bounds[0] or opened_row.created_at >= bounds[0])
                and (not bounds[1] or opened_row.created_at < bounds[1])
            ):
                continue
            if not _matches(params, opened_row.title, opened_row.description):
                continue
            seen.add((opened_row.target_kind, opened_row.target_id))
            cards.append(
                _card(
                    "LEARNING_PROGRESS",
                    "PROGRESS",
                    f"opened:{opened_row.target_id}",
                    opened_row.title,
                    "打开过资料或讲解；打开不代表看完或掌握。",
                    now,
                    target=LookupTarget(
                        type=opened_row.target_kind,
                        id=opened_row.target_id,
                        revision=opened_row.target_version,
                    ),
                    route=opened_row.route,
                    recorded_at=opened_row.created_at,
                )
            )
    for kind, (model, timestamp) in models.items():
        if params.content_type not in (None, kind):
            continue
        conditions = [model.owner_user_id == runtime.owner_user_id]
        if kind == "QUIZ":
            # Creating a quiz is not a scored learning event. A date query
            # includes only actual attempts/completion inside its time window.
            attempt_sessions = select(QuizAttempt.session_id).where(
                QuizAttempt.owner_user_id == runtime.owner_user_id,
                QuizAttempt.attempt_no.is_not(None),
                *_time_filter(QuizAttempt.created_at, bounds),
            )
            conditions.append(
                or_(
                    QuizSession.id.in_(attempt_sessions),
                    and_(
                        QuizSession.completed_at.is_not(None),
                        *_time_filter(QuizSession.completed_at, bounds),
                    ),
                )
            )
        else:
            conditions.extend(_time_filter(timestamp, bounds))
        if kind != "CODE":
            conditions.append(model.stage == runtime.expected_stage)
        if kind == "LESSON":
            conditions.append(LessonSession.conversation_type == "LESSON")
        for row in await db.scalars(select(model).where(*conditions).order_by(timestamp.desc())):
            target, route, notice = None, None, None
            recorded_at = getattr(row, timestamp.key)
            if kind == "LESSON":
                chapter = await db.get(Chapter, row.chapter_id)
                title = chapter.title if chapter else "课堂记录"
                description = "课堂活动完成" if row.lifecycle == "COMPLETED" else "课堂进行中"
                target = LookupTarget(type="LESSON", id=str(row.id))
                route = f"/conversations?session={row.id}"
            elif kind == "WATCHING":
                visible = await _resolve_visible_target(
                    db,
                    viewer=viewer,
                    kind="RESOURCE",
                    target_id=str(row.resource_id),
                    settings=runtime.settings,
                    require_file=False,
                )
                if not visible:
                    continue
                title, route = visible["title"], visible["route"]
                notice = visible.get("content_notice")
                # A6 adds viewed_at; absence never gets synthesized from completion.
                viewed_at = getattr(row, "viewed_at", None)
                resource = await db.get(Resource, row.resource_id)
                description = (
                    "已看完（播放器报告，不代表掌握）"
                    if viewed_at
                    else "打开过讲解；尚无独立看完记录"
                )
                if resource.interactive_purpose == "GAME":
                    description = "互动活动完成" if row.status == "COMPLETED" else "互动活动进行中"
                target = LookupTarget(
                    type="RESOURCE", id=str(row.resource_id), revision=str(row.revision_id)
                )
            elif kind == "QUIZ":
                title = row.source_title or "随堂练习"
                attempts = list(
                    await db.scalars(
                        select(QuizAttempt)
                        .where(
                            QuizAttempt.session_id == row.id,
                            QuizAttempt.owner_user_id == runtime.owner_user_id,
                            QuizAttempt.attempt_no.is_not(None),
                            *_time_filter(QuizAttempt.created_at, bounds),
                        )
                        .order_by(QuizAttempt.created_at, QuizAttempt.id)
                    )
                )
                latest = {attempt.question_id: attempt for attempt in attempts}
                correct = sum(attempt.is_correct is True for attempt in latest.values())
                completed_in_window = bool(
                    row.completed_at
                    and (not bounds[0] or row.completed_at >= bounds[0])
                    and (not bounds[1] or row.completed_at < bounds[1])
                )
                event_times = [attempt.created_at for attempt in attempts]
                if completed_in_window:
                    event_times.append(row.completed_at)
                recorded_at = max(event_times)
                if any(bounds):
                    activity_status = (
                        "练习在查询时间内完成"
                        if completed_in_window
                        else "当前练习已完成"
                        if row.status == "COMPLETED"
                        else "当前练习进行中"
                    )
                    description = (
                        f"查询时间内：作答 {len(attempts)} 次，"
                        f"涉及 {len(latest)}/{row.question_count} 题，"
                        f"最近作答答对 {correct} 题；{activity_status}"
                    )
                else:
                    description = (
                        f"{'练习完成' if row.status == 'COMPLETED' else '练习进行中'} · "
                        f"已答 {len(latest)}/{row.question_count} 题，最近作答答对 {correct} 题"
                    )
                target = LookupTarget(type="QUIZ", id=str(row.id))
                route = f"/practice/sessions/{row.id}"
            else:
                task = await db.scalar(
                    select(CodeTaskRevision).where(
                        CodeTaskRevision.task_id == row.task_id,
                        CodeTaskRevision.revision == row.task_revision,
                    )
                )
                if (
                    not task
                    or task.chapter_binding.get("stage") != runtime.expected_stage
                    or task.status not in ("DRAFT", "PUBLISHED")
                ):
                    continue
                title = task.title
                execution = {
                    "QUEUED": "排队中",
                    "RUNNING": "运行中",
                    "SUCCEEDED": "运行成功",
                    "FAILED": "运行失败",
                    "TIMEOUT": "超时",
                    "OUTPUT_LIMIT": "输出超限",
                    "UNAVAILABLE": "暂不可用",
                    "SYSTEM_ERROR": "系统错误",
                    "CANCELLED": "已取消",
                }.get(row.execution_status, "尚未执行")
                correctness = {
                    "PASSED": "通过",
                    "PARTIAL": "部分通过",
                    "FAILED": "未通过",
                    "NOT_VERIFIED": "尚未判分",
                }.get(row.correctness_status, "尚未判分")
                description = f"编程执行：{execution}；判分：{correctness}"
                if row.purpose == "EXAMPLE":
                    description = f"示例运行：{execution}（示例运行不计成绩）"
                elif row.deterministic_score is not None:
                    description += f"；已记录成绩：{row.deterministic_score:g}"
                target = LookupTarget(type="CODE_RUN", id=str(row.id))
                route = f"/code?task={row.task_id}&revision={row.task_revision}&run={row.id}"
            if _matches(params, title, description):
                cards.append(
                    _card(
                        "LEARNING_PROGRESS",
                        "PROGRESS",
                        f"{kind.lower()}:{row.id}",
                        title,
                        description,
                        now,
                        target=target,
                        route=route,
                        recorded_at=recorded_at,
                        notice=notice,
                    )
                )
    cards.sort(key=lambda card: card.recorded_at or "", reverse=True)
    return result_for("LEARNING_PROGRESS", cards, params, now, capped=capped)
