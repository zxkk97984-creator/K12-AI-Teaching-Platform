"""Versioned synthetic student reading and guided-animation content.

The canonical text is packaged in curriculum; a scene may refer to it by id,
version and section, but never supplies the authoritative teaching text.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.content.service import viewer_scope_from_profile
from app.modules.identity.models import LearnerProfile
from app.modules.interactive.service import InteractiveError, owned_session

_CONTENT_PATH = (
    Path(__file__).resolve().parents[4]
    / "curriculum/source/synthetic/k12-demo-v1/student-content.json"
)


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    return json.loads(_CONTENT_PATH.read_text(encoding="utf-8"))


def visible_picturebooks(stage: str) -> list[dict[str, Any]]:
    content = catalog()
    return [
        {**book, "version": content["version"], "is_test_fixture": True}
        for book in content["picturebooks"]
        if stage in book["stage"]
    ]


def visible_guided_animation(stage: str) -> dict[str, Any] | None:
    content = catalog()
    for item in content["guided_animations"]:
        if item["stage"] == stage:
            return {**item, "version": content["version"], "is_test_fixture": True}
    return None


def bind_scene(scene: dict[str, Any] | None, *, stage: str) -> dict[str, Any] | None:
    if not scene:
        return scene
    kind = scene.get("content_kind")
    if kind not in {"PICTUREBOOK", "GUIDED_ANIMATION"}:
        return scene
    index = scene.get("section_index")
    if not isinstance(index, int) or isinstance(index, bool):
        raise ValueError("学习内容位置无效")
    version = catalog()["version"]
    if scene.get("content_version") != version:
        raise ValueError("学习内容版本已变化，请刷新页面")
    if kind == "PICTUREBOOK":
        item = next(
            (book for book in visible_picturebooks(stage) if book["id"] == scene.get("content_id")),
            None,
        )
        if item is None or not 0 <= index < len(item["pages"]):
            raise ValueError("绘本当前学段不可用")
        page = item["pages"][index]
        return {
            **scene,
            "visible_section": f"{item['title']} · {page['title']}",
            "selected_text": page["text"],
            "knowledge_points": [item["topic"]],
        }
    item = visible_guided_animation(stage)
    if item is None or scene.get("content_id") != item["id"] or not 0 <= index < len(item["steps"]):
        raise ValueError("动画当前学段不可用")
    return {
        **scene,
        "visible_section": f"{item['title']} · 第 {index + 1} 步",
        "selected_text": item["steps"][index],
        "knowledge_points": [item["topic"]],
    }


async def bind_interactive_scene(
    db: AsyncSession,
    *,
    scene: dict[str, Any],
    owner_id: uuid.UUID,
    profile: LearnerProfile | None,
    settings: Settings,
) -> dict[str, Any]:
    """Replace iframe/client text with the fixed, owner-visible revision metadata."""
    if profile is None or not profile.stage:
        raise ValueError("请先设置学习阶段")
    try:
        session_id = uuid.UUID(scene.get("interactive_session_id") or "")
        content_id = uuid.UUID(scene.get("content_id") or "")
        revision_id = uuid.UUID(scene.get("content_version") or "")
    except ValueError as caught:
        raise ValueError("互动活动引用无效") from caught
    try:
        activity, resource, revision = await owned_session(
            db,
            session_id=session_id,
            owner_id=owner_id,
            viewer=viewer_scope_from_profile(profile, settings),
            settings=settings,
        )
    except InteractiveError as caught:
        raise ValueError(caught.message) from caught
    if activity.resource_id != content_id or activity.revision_id != revision_id:
        raise ValueError("互动内容与活动版本不一致")
    manifest = revision.manifest
    requested_scene = scene.get("interactive_scene_id")
    current_scene_id = activity.current_scene_id or manifest["scenes"][0]["id"]
    if requested_scene != current_scene_id:
        raise ValueError("请先保存当前场景，再向老师提问")
    current = next((item for item in manifest["scenes"] if item["id"] == current_scene_id), None)
    if current is None:
        raise ValueError("互动场景不存在")
    prompt_id = scene.get("interactive_prompt_id")
    prompt = next((item for item in manifest["prompts"] if item["id"] == prompt_id), None)
    if prompt_id and (prompt is None or prompt["scene_id"] != current_scene_id):
        raise ValueError("当前场景没有这个预设问题")
    summary = current.get("summary") or manifest.get("summary") or resource.description
    return {
        **scene,
        "page_type": "INTERACTIVE",
        "activity_type": resource.interactive_purpose,
        "visible_section": f"{resource.title} · {current['title']}",
        "selected_text": (
            f"场景摘要：{summary}" + (f"\n预设问题：{prompt['text']}" if prompt else "")
        ),
        "knowledge_points": manifest.get("knowledge_points", []),
        "content_id": str(resource.id),
        "content_version": str(revision.id),
    }
