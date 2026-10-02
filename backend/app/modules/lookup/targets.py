"""Resolve stored targets against today's owner, visibility and version rules."""

import uuid

from sqlalchemy import select

from app.modules.assessment.models import QuizSession
from app.modules.codelab.models import CodeRun, CodeTaskRevision
from app.modules.content.service import visible_chapter_detail
from app.modules.learning.models import PicturebookProgress
from app.modules.learning.study_content import visible_picturebooks
from app.modules.learning.study_router import _resolve_visible_target
from app.modules.lookup.schemas import LookupTarget
from app.modules.lookup.service import LookupRuntime, _viewer
from app.modules.teaching.models import LessonSession


async def resolve_target(runtime: LookupRuntime, target: LookupTarget) -> str | None:
    viewer = await _viewer(runtime)
    db = runtime.db
    try:
        if target.type == "PICTUREBOOK":
            book = next(
                (
                    book
                    for book in visible_picturebooks(runtime.expected_stage)
                    if book["id"] == target.id
                ),
                None,
            )
            progress = await db.get(PicturebookProgress, (runtime.owner_user_id, target.id))
            if book and progress and (not target.revision or target.revision == book["version"]):
                return f"/picturebooks/{book['id']}"
            return None
        if target.type == "ANIMATION":
            animation = await _resolve_visible_target(
                db,
                viewer=viewer,
                kind="ANIMATION",
                target_id=target.id,
                settings=runtime.settings,
            )
            if animation and (
                not target.revision or target.revision == animation.get("target_version")
            ):
                return animation["route"]
            return None
        identifier = uuid.UUID(target.id)
        if target.type == "CHAPTER":
            detail = await visible_chapter_detail(
                db,
                chapter_id=identifier,
                viewer=viewer,
                revision=int(target.revision) if target.revision else None,
            )
            return f"/chapters/{identifier}?revision={detail.revision}" if detail else None
        if target.type == "RESOURCE":
            resource = await _resolve_visible_target(
                db,
                viewer=viewer,
                kind="RESOURCE",
                target_id=target.id,
                settings=runtime.settings,
            )
            if (
                resource
                and resource.get("available", True)
                and (not target.revision or target.revision == resource.get("target_version"))
            ):
                return resource["route"]
            return None
        model = {"QUIZ": QuizSession, "LESSON": LessonSession, "CODE_RUN": CodeRun}[target.type]
        row = await db.scalar(
            select(model).where(
                model.id == identifier,
                model.owner_user_id == runtime.owner_user_id,
            )
        )
        if row is None:
            return None
        if target.type == "CODE_RUN":
            task = await db.scalar(
                select(CodeTaskRevision).where(
                    CodeTaskRevision.task_id == row.task_id,
                    CodeTaskRevision.revision == row.task_revision,
                    CodeTaskRevision.status.in_(["DRAFT", "PUBLISHED"]),
                )
            )
            if task and task.chapter_binding.get("stage") == runtime.expected_stage:
                return f"/code?task={row.task_id}&revision={row.task_revision}&run={row.id}"
            return None
        if row.stage != runtime.expected_stage:
            return None
        if target.type == "LESSON":
            if row.chapter_id and not await visible_chapter_detail(
                db,
                chapter_id=row.chapter_id,
                viewer=viewer,
            ):
                return None
            return f"/conversations?session={identifier}"
        return f"/practice/sessions/{identifier}"
    except (ValueError, TypeError, KeyError):
        return None
