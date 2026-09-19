"""Server-side chapter material + frozen Designer request builder (T22 V1).

The Designer only ever sees a *server-derived* request: the chapter revision
bound to the job decides the stage, objectives and knowledge context. Nothing
comes from the browser, and a revision without real source text is refused
instead of letting the model invent a lesson (same rule as T15 QA17).

Only the frozen ``k12.designer.request.v1`` shape is produced; the tests assert
it validates against ``platform/knodo/contracts/designer-request.schema.json``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.authoring.errors import AuthoringError
from app.modules.content.models import Chapter, ChapterReviewState, ChapterRevision
from app.modules.resources.animation_service import load_definitions

DESIGNER_REQUEST_SCHEMA_VERSION = "k12.designer.request.v1"
STAGE_VALUES = frozenset({"PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"})
MAX_CONTEXT_ITEMS = 8
MAX_CONTEXT_TEXT = 8000
MAX_OBJECTIVES = 12
# Frozen draft templates -> locally registered animation templates. A frozen
# template without a registered definition is simply not offered to the model.
FROZEN_TEMPLATE_ORDER = ("ADJACENT_SORT", "BINARY_SEARCH")
FROZEN_TO_REGISTRY_TEMPLATE = {"ADJACENT_SORT": "SORT_STEPS", "BINARY_SEARCH": "BINARY_SEARCH"}
AUTHOR_INSTRUCTION = (
    "输出结构化教学规格（计划、脚本、活动、动画引用）。"
    "asset_requests 只登记「需要人工提供的素材」，不代表文件已经存在，"
    "不得声称 PPT／图像／视频已生成。"
)
_TEXT_KEYS = ("text", "caption", "alt", "title")


@dataclass(frozen=True)
class AuthoringMaterial:
    chapter_id: uuid.UUID
    revision_id: uuid.UUID
    chapter_slug: str
    chapter_title: str
    revision_number: int
    curriculum_revision: str
    stage: str
    objectives: tuple[str, ...]
    knowledge_context: tuple[dict[str, Any], ...]


def _block_text(block: dict[str, Any]) -> str:
    parts = [
        block[key].strip()
        for key in _TEXT_KEYS
        if isinstance(block.get(key), str) and block[key].strip()
    ]
    return " ".join(parts)


async def load_authoring_material(db: AsyncSession, *, revision_id: uuid.UUID) -> AuthoringMaterial:
    """Load one exact revision. Missing/withdrawn/empty material is refused."""

    revision = await db.scalar(select(ChapterRevision).where(ChapterRevision.id == revision_id))
    if revision is None:
        raise AuthoringError("AUTHORING_REVISION_NOT_FOUND", "章节版本不存在", 404)
    chapter = await db.scalar(select(Chapter).where(Chapter.id == revision.chapter_id))
    if chapter is None:  # pragma: no cover - FK enforced
        raise AuthoringError("AUTHORING_REVISION_NOT_FOUND", "章节不存在", 404)
    review_state = await db.scalar(
        select(ChapterReviewState).where(ChapterReviewState.revision_id == revision.id)
    )
    if review_state is not None and review_state.publication_status == "WITHDRAWN":
        raise AuthoringError("AUTHORING_REVISION_WITHDRAWN", "章节版本已撤回，不能生成教学包", 422)
    if revision.stage not in STAGE_VALUES:
        raise AuthoringError("AUTHORING_STAGE_UNSUPPORTED", "不支持的学段", 422)

    context: list[dict[str, Any]] = []
    source_id = f"chapter:{chapter.stable_slug}"[:160]
    for index, block in enumerate(revision.body or []):
        if not isinstance(block, dict):
            continue
        text = _block_text(block)
        if not text:
            continue
        context.append(
            {
                "source_id": source_id,
                "revision": str(revision.revision),
                "locator": f"block:{index}",
                "text": text[:MAX_CONTEXT_TEXT],
            }
        )
        if len(context) >= MAX_CONTEXT_ITEMS:
            break
    if not context:
        raise AuthoringError(
            "AUTHORING_NO_SOURCE_MATERIAL", "章节没有可引用的正文，不能生成教学包", 422
        )

    objectives: list[str] = []
    for index, objective in enumerate(revision.objectives or []):
        text = objective.strip() if isinstance(objective, str) else ""
        objectives.append(text[:160] if text else f"{chapter.stable_slug}:obj:{index + 1}")
    if not objectives:
        objectives = [f"{chapter.stable_slug}:obj:1"]

    return AuthoringMaterial(
        chapter_id=chapter.id,
        revision_id=revision.id,
        chapter_slug=chapter.stable_slug,
        chapter_title=chapter.title,
        revision_number=revision.revision,
        curriculum_revision=f"{chapter.stable_slug}:r{revision.revision}",
        stage=revision.stage,
        objectives=tuple(objectives[:MAX_OBJECTIVES]),
        knowledge_context=tuple(context),
    )


def registry_definition_for(frozen_template: str) -> dict[str, Any] | None:
    """The locally registered definition a frozen template maps to, if any."""

    registry_template = FROZEN_TO_REGISTRY_TEMPLATE.get(frozen_template)
    if registry_template is None:
        return None
    candidates = [entry for entry in load_definitions() if entry["template"] == registry_template]
    if not candidates:
        return None
    # Prefer formally published definitions over fixtures; id keeps it stable.
    candidates.sort(
        key=lambda entry: (
            bool(entry.get("is_test_fixture")),
            entry.get("publication_status") != "PUBLISHED",
            str(entry.get("id", "")),
        )
    )
    return candidates[0]


def available_frozen_templates() -> list[str]:
    return [item for item in FROZEN_TEMPLATE_ORDER if registry_definition_for(item) is not None]


def build_package_request(material: AuthoringMaterial, *, request_id: str) -> dict[str, Any]:
    """The frozen ``k12.designer.request.v1`` payload for LESSON_PACKAGE_DRAFT."""

    return {
        "schema_version": DESIGNER_REQUEST_SCHEMA_VERSION,
        "request_id": request_id[:160],
        "operation": "LESSON_PACKAGE_DRAFT",
        "chapter_id": str(material.chapter_id),
        "curriculum_revision": material.curriculum_revision[:160],
        "stage": material.stage,
        "objective_ids": [item[:160] for item in material.objectives],
        "knowledge_context": [dict(item) for item in material.knowledge_context],
        "allowed_resource_ids": [],
        "quiz_spec": None,
        "lesson_spec": {
            "allowed_animation_templates": available_frozen_templates(),
            "asset_requests_allowed": True,
            "author_instruction": AUTHOR_INSTRUCTION,
        },
    }


__all__ = [
    "AUTHOR_INSTRUCTION",
    "AuthoringMaterial",
    "DESIGNER_REQUEST_SCHEMA_VERSION",
    "available_frozen_templates",
    "build_package_request",
    "load_authoring_material",
    "registry_definition_for",
]
