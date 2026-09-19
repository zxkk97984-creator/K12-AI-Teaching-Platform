"""Trusted Designer request construction (T15 G1/G7).

Nothing here comes from a client payload: the chapter revision, knowledge
context, objective ids, source whitelist, question count, difficulty and
question types are all derived from server-side rows plus the T14 policy.

Source ids follow the same convention as the Tutor context
(``chapter:<stable_slug>``), so a quiz source ref can be checked against the
chapter it was generated for.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.knodo.schema_models import CONTRACTS_DIR
from app.modules.assessment.errors import DesignerRequestInvalid
from app.modules.assessment.validation import SUPPORTED_TYPES, QuizExpectation
from app.modules.content.models import (
    Chapter,
    ChapterReviewState,
    ChapterRevision,
    Release,
)
from app.modules.learning.policy import LearningPolicy, build_policy

DESIGNER_REQUEST_SCHEMA_VERSION = "k12.designer.request.v1"
MAX_CONTEXT_ITEMS = 8
MAX_CONTEXT_TEXT = 8000
# Conservative first release: drafts start at the easiest band; a later card may
# pass an explicit policy snapshot once evidence exists (never HARD by grade).
DEFAULT_DESIGN_DIFFICULTY = "EASY"
_TEXT_KEYS = ("text", "caption", "alt", "title")


@dataclass(frozen=True)
class ChapterMaterial:
    chapter_id: uuid.UUID
    revision_id: uuid.UUID
    chapter_slug: str
    chapter_title: str
    revision_number: int
    curriculum_revision: str
    stage: str
    objectives: tuple[str, ...]
    knowledge_context: tuple[dict[str, Any], ...]
    release_is_test_fixture: bool

    @property
    def source_id(self) -> str:
        return f"chapter:{self.chapter_slug}"[:160]

    def source_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple((item["source_id"], item["revision"]) for item in self.knowledge_context)


def _block_text(block: dict[str, Any]) -> str:
    parts = [
        block[key].strip()
        for key in _TEXT_KEYS
        if isinstance(block.get(key), str) and block[key].strip()
    ]
    return " ".join(parts)


async def load_chapter_material(db: AsyncSession, *, chapter_id: uuid.UUID) -> ChapterMaterial:
    """Latest non-withdrawn revision of one chapter (server-side truth)."""

    row = (
        await db.execute(
            select(ChapterRevision, Chapter, Release, ChapterReviewState)
            .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
            .join(Release, Release.id == ChapterRevision.release_id)
            .join(ChapterReviewState, ChapterReviewState.revision_id == ChapterRevision.id)
            .where(ChapterRevision.chapter_id == chapter_id)
            .order_by(ChapterRevision.revision.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise DesignerRequestInvalid("章节当前没有可用版本", code="CHAPTER_NOT_FOUND")
    revision, chapter, release, review_state = row
    if review_state.publication_status == "WITHDRAWN":
        raise DesignerRequestInvalid("章节版本已撤回", code="CHAPTER_WITHDRAWN")

    context: list[dict[str, Any]] = []
    for index, block in enumerate(revision.body or []):
        if not isinstance(block, dict):
            continue
        text = _block_text(block)
        if not text:
            continue
        context.append(
            {
                "source_id": f"chapter:{chapter.stable_slug}"[:160],
                "revision": str(revision.revision),
                "locator": f"block:{index}",
                "text": text[:MAX_CONTEXT_TEXT],
            }
        )
        if len(context) >= MAX_CONTEXT_ITEMS:
            break
    if not context:
        # No material: refuse instead of letting the model invent content (QA17).
        raise DesignerRequestInvalid(
            "章节没有可引用的正文，不能生成题稿", code="NO_SOURCE_MATERIAL"
        )

    return ChapterMaterial(
        chapter_id=chapter.id,
        revision_id=revision.id,
        chapter_slug=chapter.stable_slug,
        chapter_title=chapter.title,
        revision_number=revision.revision,
        curriculum_revision=f"{chapter.stable_slug}:r{revision.revision}",
        stage=revision.stage,
        objectives=tuple(revision.objectives or []),
        knowledge_context=tuple(context),
        release_is_test_fixture=bool(release.is_test_fixture),
    )


def load_designer_fixture_allowance() -> dict[str, Any]:
    """Dev/test allowance taken from the frozen synthetic quiz example.

    Only applied when the gateway runs in fixture mode *and* the chapter comes
    from a synthetic release, so production validation stays strict. The
    allowance expands the trusted whitelist with ids the frozen fixture echoes
    back; it never weakens answer/shape rules.
    """

    path = Path(CONTRACTS_DIR) / "examples" / "quiz-draft.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    objective_ids: list[str] = []
    sources: list[dict[str, str]] = []
    for question in payload.get("questions", []):
        objective = question.get("objective_id")
        if isinstance(objective, str) and objective not in objective_ids:
            objective_ids.append(objective)
        for ref in question.get("source_refs", []):
            pair = {"source_id": ref.get("source_id"), "revision": ref.get("revision")}
            if isinstance(pair["source_id"], str) and isinstance(pair["revision"], str):
                if pair not in sources:
                    sources.append(pair)
    return {
        "objective_ids": objective_ids,
        "sources": sources,
        "notice": "LOCAL_FIXTURE_ALLOWANCE_FROM_FROZEN_SYNTHETIC_EXAMPLE",
    }


def design_policy(stage: str) -> LearningPolicy:
    return build_policy(
        stage=stage,
        grade=None,  # a design job never invents a grade
        preferred_style="AUTO",
        evidence_level="NONE",  # no student evidence is used to draft questions
        proactive_guidance_enabled=True,
    )


def build_designer_request(
    material: ChapterMaterial,
    *,
    request_id: str,
    allowance: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], QuizExpectation]:
    """Build the frozen designer-request payload plus its validation expectation."""

    policy = design_policy(material.stage)
    question_types = tuple(
        item for item in policy.allowed_question_types if item in SUPPORTED_TYPES
    )
    if not question_types:
        raise DesignerRequestInvalid("当前学段没有可用的题型", code="NO_QUESTION_TYPES")
    difficulty = DEFAULT_DESIGN_DIFFICULTY
    if difficulty not in policy.allowed_difficulties:  # pragma: no cover - bands always allow EASY
        raise DesignerRequestInvalid("默认难度不在策略允许范围内", code="DIFFICULTY_NOT_ALLOWED")

    # Objective ids stay human-meaningful (the learner's real objective text)
    # and are truncated to the schema bound; opaque local ids are only a
    # fallback when the revision has no objective text at all.
    objective_ids: list[str] = []
    for index, objective in enumerate(material.objectives):
        text = objective.strip() if isinstance(objective, str) else ""
        objective_ids.append(text[:160] if text else f"{material.chapter_slug}:obj:{index + 1}")
    if not objective_ids:
        objective_ids = [f"{material.chapter_slug}:obj:1"]
    sources: list[tuple[str, str]] = list(material.source_pairs())
    if allowance:
        for objective in allowance.get("objective_ids", []):
            if objective not in objective_ids:
                objective_ids.append(objective)
        for ref in allowance.get("sources", []):
            pair = (ref.get("source_id"), ref.get("revision"))
            if pair not in sources:
                sources.append(pair)

    payload = {
        "schema_version": DESIGNER_REQUEST_SCHEMA_VERSION,
        "request_id": request_id,
        "operation": "QUIZ_DRAFT",
        "chapter_id": str(material.chapter_id),
        "curriculum_revision": material.curriculum_revision,
        "stage": material.stage,
        "objective_ids": objective_ids,
        "knowledge_context": [dict(item) for item in material.knowledge_context],
        "allowed_resource_ids": [],
        "quiz_spec": {
            "count": policy.max_quiz_questions,
            "difficulty": difficulty,
            "question_types": list(question_types),
            "misconception_summary": "",
        },
        "lesson_spec": None,
    }
    expectation = QuizExpectation(
        request_id=request_id,
        chapter_id=str(material.chapter_id),
        curriculum_revision=material.curriculum_revision,
        stage=material.stage,
        count=policy.max_quiz_questions,
        difficulty=difficulty,
        question_types=question_types,
        objective_ids=tuple(objective_ids),
        sources=tuple(sources),
    )
    return payload, expectation
