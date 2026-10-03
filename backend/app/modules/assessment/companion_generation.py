"""Student-authored requests in a continuous, owner-scoped conversation."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.modules.assessment.models import GenerationJob
from app.modules.assessment.service import (
    _request_hash,
    enqueue_conversation_generation,
    enqueue_student_generation,
)
from app.modules.content.service import viewer_scope_from_profile, visible_chapter_detail
from app.modules.learning.policy import build_policy
from app.modules.learning.study_content import bind_interactive_scene, bind_scene
from app.modules.teaching.models import ConversationMessage, LessonSession


async def enqueue_companion_quiz(db, *, body, profile, owner, settings):
    conversation = await db.scalar(
        select(LessonSession).where(
            LessonSession.id == body.conversation_id,
            LessonSession.owner_user_id == owner.id,
            LessonSession.stage == profile.stage,
            LessonSession.archived_at.is_(None),
        )
    )
    if conversation is None:
        raise HTTPException(404, "会话不存在或学段已变化")
    if conversation.conversation_type != "FREE":
        raise HTTPException(409, "请新建自由对话，继续本次学习")
    digest = _request_hash(body.model_dump(mode="json"))
    existing = await db.scalar(
        select(GenerationJob).where(
            GenerationJob.owner_user_id == owner.id,
            GenerationJob.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        expected = (existing.request_config or {}).get("student_request_hash") or (
            existing.request_config or {}
        ).get("source_snapshot", {}).get("student_request_hash")
        if expected != digest:
            raise HTTPException(409, "同一幂等键对应不同的出题请求")
        return existing
    policy = build_policy(
        stage=profile.stage,
        grade=profile.grade,
        preferred_style=profile.preferred_style,
        evidence_level="NONE",
        proactive_guidance_enabled=profile.proactive_guidance_enabled,
    )
    if body.difficulty and body.difficulty not in policy.allowed_difficulties:
        raise HTTPException(422, "当前学段不支持该难度")
    if body.ordinary_question_types and set(body.ordinary_question_types) - set(
        policy.allowed_question_types
    ):
        raise HTTPException(422, "包含当前学段不支持的题型")
    scene = body.scene.model_dump(mode="json") if body.scene else {}
    chapter_id = body.chapter_id or scene.get("chapter_id")
    message_id = uuid.uuid5(owner.id, "companion-quiz:" + body.idempotency_key)
    count = body.ordinary_question_count if body.ordinary_question_count is not None else 5
    topic = body.knowledge_point
    chapter = None
    if chapter_id:
        try:
            chapter_id = uuid.UUID(str(chapter_id))
        except ValueError as exc:
            raise HTTPException(422, "章节引用无效") from exc
        chapter = await visible_chapter_detail(
            db, chapter_id=chapter_id, viewer=viewer_scope_from_profile(profile, settings)
        )
        if chapter is None:
            raise HTTPException(404, "章节不可用")
        requested_revision = body.chapter_revision or scene.get("chapter_revision")
        if requested_revision is not None and requested_revision != chapter.revision:
            raise HTTPException(409, "章节版本已变化，请重新读取后出题")
        block_id = scene.get("content_block_id")
        if block_id and not any(block.block_id == block_id for block in chapter.blocks):
            raise HTTPException(422, "当前章节没有该段落，请重新读取后出题")
        scene = {
            **scene,
            "chapter_title": chapter.title[:200],
            "chapter_revision": chapter.revision,
        }
        topic = topic or chapter.title
    else:
        if scene.get("content_kind") == "INTERACTIVE":
            scene = await bind_interactive_scene(
                db, scene=scene, owner_id=owner.id, profile=profile, settings=settings
            )
        else:
            scene = bind_scene(scene, stage=profile.stage) or {}
        latest = await db.scalar(
            select(ConversationMessage)
            .where(
                ConversationMessage.session_id == conversation.id,
                ConversationMessage.owner_user_id == owner.id,
                ConversationMessage.role == "ASSISTANT",
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        source_text = scene.get("selected_text") or (latest.content_markdown if latest else "")
        topic = topic or scene.get("visible_section") or (conversation.title if latest else None)
        if not topic and "本章" not in body.student_request:
            import re

            match = re.search(r"(?:围绕|关于|针对)(.+?)(?:生成|出|练习)", body.student_request)
            topic = match.group(1).strip() if match else None
        if "本章" in body.student_request or not topic:
            raise HTTPException(422, "请在章节中出题，或说明要练习的知识点")
        source_text = source_text or topic
    await db.execute(
        insert(ConversationMessage)
        .values(
            id=message_id,
            session_id=conversation.id,
            owner_user_id=owner.id,
            role="USER",
            content_markdown=body.student_request,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    if chapter:
        job = await enqueue_student_generation(
            db,
            settings=settings,
            requester=owner,
            chapter_id=chapter_id,
            revision_id=chapter.revision_id,
            idempotency_key=body.idempotency_key,
            question_count=count,
            difficulty=body.difficulty,
            question_types=body.ordinary_question_types,
            conversation_id=conversation.id,
            message_id=message_id,
            student_request_hash=digest,
        )
    else:
        job = await enqueue_conversation_generation(
            db,
            settings=settings,
            requester=owner,
            snapshot={
                "conversation_id": str(conversation.id),
                "message_id": str(message_id),
                "stage": profile.stage,
                "topic": topic[:160],
                "text": source_text[:8000],
                "locator": "student-request-and-page-context",
                "student_request_hash": digest,
                "fixture": settings.gateway_mode == "fixture",
            },
            idempotency_key=body.idempotency_key,
            question_count=count,
            difficulty=body.difficulty,
            question_types=body.ordinary_question_types,
        )
    job.request_config = {
        **(job.request_config or {}),
        "student_request": body.student_request,
        "scene": scene,
    }
    job.request_summary = {
        **(job.request_summary or {}),
        "topic": topic[:160],
        "count": count,
        "chapter_id": str(chapter_id) if chapter else None,
        "generated_count": 0,
    }
    await db.commit()
    return job
