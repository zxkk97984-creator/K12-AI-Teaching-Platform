"""Build the local semantic teaching request from stored chapter content.

The T03 ``teaching-request`` contract is the local semantic request. Its
knowledge sources and allowed resource/action sets are derived **from the
stored chapter revision**, so a model cannot invent a resource the student
could not otherwise open (QA13).

Dev/test only: when the chapter release is an explicitly marked synthetic
fixture *and* the gateway runs in fixture mode, the session records a
``fixture_allowance`` taken from the same frozen example the fixture backend
serves. That allowance is stored on the session, surfaced on the card as
``fixture: true``, and never renders clickable resources.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.integrations.knodo.schema_models import CONTRACTS_DIR
from app.modules.resources.service import allowed_resource_ids_for_teaching

POLICY_REVISION = "local-teaching-policy-v1"
# Animation ids come from the server-side registry, never from model prose.
# This is a shape whitelist only; authorisation happens in resources/.
_SAFE_ANIMATION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,118}$")
FIXTURE_NOTICE = "SYNTHETIC_FIXTURE_NOT_REAL_KNODO"

_ACTION_FOR_BLOCK = {
    "RESOURCE": ("OPEN_RESOURCE", "allowed_resource_ids"),
    "ANIMATION": ("OPEN_ANIMATION", "allowed_animation_ids"),
    "CODE_TASK": ("OPEN_CODE_TASK", "allowed_code_task_ids"),
}


def _chapter_text(blocks: list[dict[str, Any]], *, limit: int = 8000) -> str:
    parts: list[str] = []
    for block in blocks:
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
        if sum(len(part) for part in parts) >= limit:
            break
    return "\n\n".join(parts)[:limit] or "（本章节暂无正文）"


def _knowledge_sources(
    blocks: list[dict[str, Any]], *, chapter_slug: str, revision: int
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for block in blocks:
        source = block.get("source")
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        locator = source.get("locator")
        if isinstance(source_id, str) and source_id and isinstance(locator, str) and locator:
            sources.append(
                {
                    "source_id": source_id[:160],
                    "revision": str(source.get("revision") or revision)[:160],
                    "locator": locator[:300],
                    "text": str(block.get("text") or "")[:8000] or "（无文本）",
                }
            )
        if len(sources) >= 8:
            break
    if sources:
        return sources
    return [
        {
            "source_id": f"chapter:{chapter_slug}"[:160],
            "revision": str(revision),
            "locator": "chapter",
            "text": _chapter_text(blocks),
        }
    ]


def build_session_context(
    *,
    chapter_slug: str,
    chapter_id: str,
    chapter_title: str,
    revision_number: int,
    revision_id: str,
    stage: str,
    objectives: list[str],
    blocks: list[dict[str, Any]],
    authorized_resource_ids: list[str] | None = None,
    authorized_animation_ids: list[str] | None = None,
) -> dict[str, Any]:
    objectives = [item for item in objectives if isinstance(item, str) and item][:12]
    if not objectives:
        objectives = [f"{chapter_slug}-objective-1"]
    knowledge = _knowledge_sources(blocks, chapter_slug=chapter_slug, revision=revision_number)

    actions: list[str] = []
    allowed_ids: dict[str, list[str]] = {
        "allowed_resource_ids": [],
        "allowed_animation_ids": [],
        "allowed_code_task_ids": [],
    }
    for block in blocks:
        block_type = block.get("type")
        mapping = _ACTION_FOR_BLOCK.get(str(block_type))
        block_id = block.get("id")
        if mapping and isinstance(block_id, str) and block_id:
            action, bucket = mapping
            if action not in actions:
                actions.append(action)
            allowed_ids[bucket].append(block_id)
    if "OFFER_QUIZ" not in actions:
        actions.append("OFFER_QUIZ")

    return {
        "chapter": {"id": chapter_id, "title": chapter_title[:250], "objective_ids": objectives},
        "curriculum_revision": f"{revision_id}:{revision_number}",
        "policy_revision": POLICY_REVISION,
        "knowledge_context": knowledge,
        "allowed_actions": actions,
        "allowed_resource_ids": allowed_resource_ids_for_teaching(
            authorized_ids=authorized_resource_ids
        )[:16],
        # T21 repair: the registry-filtered set is the only source. Without an
        # injected set this is empty (fail-closed) — the chapter body never
        # authorises an animation on its own.
        "allowed_animation_ids": [
            item
            for item in (authorized_animation_ids or [])
            if isinstance(item, str) and _SAFE_ANIMATION_ID.match(item)
        ][:8],
        "allowed_code_task_ids": allowed_ids["allowed_code_task_ids"][:12],
        "allowed_phase_suggestions": ["ORIENT", "EXPLAIN", "CHECK", "PRACTICE", "REFLECT"],
        "limits": {
            "max_quiz_questions": 3,
            "allowed_difficulties": ["EASY", "MEDIUM"],
            "max_reply_chars": 1200,
        },
        "allowed_source_ids": [item["source_id"] for item in knowledge],
        "allowed_evidence_ids": [],
        "fixture_notice": FIXTURE_NOTICE,
    }


def build_free_session_context(*, stage: str) -> dict[str, Any]:
    """Build a safe, source-free context for an unconstrained student chat.

    Free conversations deliberately have no chapter knowledge or clickable
    resources. The Tutor still receives the same contract shape and can answer
    general AI/programming questions using its configured Knodo knowledge.
    """

    return {
        "chapter": {
            "id": "free-conversation",
            "title": "自由对话",
            "objective_ids": ["free-conversation"],
        },
        "curriculum_revision": "free-conversation:v1",
        "policy_revision": POLICY_REVISION,
        "knowledge_context": [],
        "allowed_actions": ["OFFER_QUIZ"],
        "allowed_resource_ids": [],
        "allowed_animation_ids": [],
        "allowed_code_task_ids": [],
        "allowed_phase_suggestions": ["ORIENT", "EXPLAIN", "CHECK", "PRACTICE", "REFLECT"],
        "limits": {
            "max_quiz_questions": 3,
            "allowed_difficulties": ["EASY", "MEDIUM"],
            "max_reply_chars": 1200,
        },
        "allowed_source_ids": [],
        "allowed_evidence_ids": [],
        "fixture_notice": FIXTURE_NOTICE,
        "learner_stage": stage,
    }


def load_fixture_allowance() -> dict[str, Any]:
    """Dev/test allowance taken from the frozen synthetic example (T10 fixture)."""

    path = Path(CONTRACTS_DIR) / "examples" / "teaching-response.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = [item["source_id"] for item in payload.get("source_refs", [])]
    actions: list[str] = []
    animation_ids: list[str] = []
    resource_ids: list[str] = []
    action = payload.get("action")
    if isinstance(action, dict):
        action_type = action.get("type")
        if isinstance(action_type, str):
            actions.append(action_type)
        if isinstance(action.get("resource_id"), str):
            if action_type == "OPEN_ANIMATION":
                animation_ids.append(action["resource_id"])
            elif action_type == "OPEN_RESOURCE":
                resource_ids.append(action["resource_id"])
    return {
        "allowed_source_ids": sources,
        "allowed_evidence_ids": list(payload.get("evidence_refs", [])),
        "allowed_actions": actions,
        "allowed_resource_ids": resource_ids,
        "allowed_animation_ids": animation_ids,
        "allowed_code_task_ids": [],
        "notice": "LOCAL_FIXTURE_ALLOWANCE_FROM_FROZEN_SYNTHETIC_EXAMPLE",
    }


def build_teaching_request(
    *,
    session_id: str,
    context: dict[str, Any],
    operation: str,
    student_input: str,
    base_revision: int,
    stage: str,
    grade: int | None,
    preferred_style: str,
    fixture_allowance: dict[str, Any] | None,
    event: str = "ASK",
    current_phase: str = "EXPLAIN",
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actions = list(context["allowed_actions"])
    resource_ids = list(context["allowed_resource_ids"])
    animation_ids = list(context["allowed_animation_ids"])
    code_task_ids = list(context["allowed_code_task_ids"])
    if fixture_allowance:
        for action in fixture_allowance.get("allowed_actions", []):
            if action not in actions:
                actions.append(action)
        resource_ids += [
            i for i in fixture_allowance.get("allowed_resource_ids", []) if i not in resource_ids
        ]
        animation_ids += [
            i for i in fixture_allowance.get("allowed_animation_ids", []) if i not in animation_ids
        ]
    return {
        "schema_version": "k12.teaching.request.v1",
        "request_id": f"run-{session_id}-{base_revision}",
        "lesson_session_id": session_id,
        "base_revision": base_revision,
        "curriculum_revision": context["curriculum_revision"],
        "policy_revision": context["policy_revision"],
        "operation": operation,
        "event": event,
        "current_phase": current_phase,
        "learner": {"stage": stage, "grade": grade, "preferred_style": preferred_style},
        "chapter": context["chapter"],
        "knowledge_context": context["knowledge_context"],
        "evidence": [],
        "allowed_actions": actions,
        "allowed_resource_ids": resource_ids,
        "allowed_animation_ids": animation_ids,
        "allowed_code_task_ids": code_task_ids,
        "allowed_phase_suggestions": context["allowed_phase_suggestions"],
        "limits": _limits_for(context, policy),
        "student_input": student_input,
        "code_feedback_facts": None,
    }


def _limits_for(context: dict[str, Any], policy: dict[str, Any] | None) -> dict[str, Any]:
    """The active policy snapshot decides quiz volume, difficulty and length."""

    limits = dict(context.get("limits", {}))
    if policy:
        limits["max_quiz_questions"] = int(
            policy.get("max_quiz_questions", limits.get("max_quiz_questions", 0))
        )
        limits["allowed_difficulties"] = list(
            policy.get("allowed_difficulties", limits.get("allowed_difficulties", ["EASY"]))
        )
        limits["max_reply_chars"] = int(
            policy.get("max_explanation_chars", limits.get("max_reply_chars", 1200))
        )
    return limits
