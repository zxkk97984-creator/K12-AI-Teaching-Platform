"""Controlled teaching animations: registry loading, filtering and parameters.

Truth model (T21):

* ``curriculum/animations/definitions.json`` is the registry. Only the two
  frozen templates ``SORT_STEPS`` and ``BINARY_SEARCH`` exist; anything else is
  dropped (fail-closed) instead of being passed to a client.
* Nothing here executes or transports code. A definition is data: template id,
  bounded parameter schema, chapter/knowledge-point binding and narration. The
  step list is produced by the front-end pure functions.
* Visibility reuses the frozen content truth: the definition's own publication
  state must allow it **and** the bound chapter revision must be visible to the
  viewer under the same rules the reader uses (``visible_chapter_detail``).
* Parameters are validated against the declared schema before a client may
  generate steps: unknown keys, wrong types, oversized arrays and out-of-range
  numbers are rejected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.models import ContentProfile
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import visible_chapter_detail

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFINITIONS_PATH = REPO_ROOT / "curriculum/animations/definitions.json"

ALLOWED_TEMPLATES = frozenset({"SORT_STEPS", "BINARY_SEARCH"})
FIXTURE_NOTICE = "测试内容，未作人工教学审校"
STAGE_BOUNDS = {
    "PRIMARY_LOWER": (1, 3),
    "PRIMARY_UPPER": (4, 6),
    "JUNIOR": (7, 9),
    "SENIOR": (10, 12),
}
DEFAULT_LIMITS = {"max_items": 12, "max_steps": 400, "min_value": -99, "max_value": 999}


class AnimationError(Exception):
    """A rejected animation request, mapped to a readable HTTP error."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AnimationNotVisible(AnimationError):
    def __init__(self) -> None:
        super().__init__("ANIMATION_NOT_VISIBLE", "动画不可用", 404)


class AnimationParamsRejected(AnimationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 422)


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def _load_raw(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFINITIONS_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": "unknown", "limits": DEFAULT_LIMITS, "definitions": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("definitions"), list):
        return {"schema_version": "unknown", "limits": DEFAULT_LIMITS, "definitions": []}
    return payload


def _valid_definition(raw: Any, limits: dict[str, int]) -> dict[str, Any] | None:
    """Strict shape check; a malformed entry is dropped, never guessed."""

    if not isinstance(raw, dict):
        return None
    template = raw.get("template")
    if template not in ALLOWED_TEMPLATES:
        return None
    stage = raw.get("stage")
    if stage not in STAGE_BOUNDS:
        return None
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier:
        return None
    schema = raw.get("param_schema")
    if not isinstance(schema, dict) or schema.get("additional_properties") is not False:
        return None
    for key, spec in (schema.get("properties") or {}).items():
        if not isinstance(key, str) or not isinstance(spec, dict):
            return None
        if spec.get("type") not in {"int_array", "int"}:
            return None
    required = schema.get("required")
    if not isinstance(required, list) or not required:
        return None
    entry = dict(raw)
    entry["limits"] = dict(limits)
    grade_min, grade_max = raw.get("grade_min"), raw.get("grade_max")
    bounds = STAGE_BOUNDS[stage]
    if grade_min is not None or grade_max is not None:
        if not isinstance(grade_min, int) or not isinstance(grade_max, int):
            return None
        if grade_min > grade_max or grade_min < bounds[0] or grade_max > bounds[1]:
            return None
    return entry


def load_definitions(path: Path | None = None) -> list[dict[str, Any]]:
    """Every valid, registered definition (no viewer filtering yet)."""

    payload = _load_raw(path)
    raw_limits = payload.get("limits")
    limits = dict(DEFAULT_LIMITS)
    if isinstance(raw_limits, dict):
        for key in DEFAULT_LIMITS:
            value = raw_limits.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                limits[key] = value
    entries: list[dict[str, Any]] = []
    for raw in payload.get("definitions", []):
        entry = _valid_definition(raw, limits)
        if entry is not None:
            entries.append(entry)
    return entries


def find_definition(identifier: str, path: Path | None = None) -> dict[str, Any] | None:
    for entry in load_definitions(path):
        if entry["id"] == identifier:
            return entry
    return None


# --------------------------------------------------------------------------- #
# visibility (reuses the frozen content truth)
# --------------------------------------------------------------------------- #
def _declaration_allows(entry: dict[str, Any], viewer: ViewerScope) -> bool:
    """Definition-level gate, mirroring the T20 fixture/published rules."""

    if viewer.profile is ContentProfile.FORMAL:
        return (
            entry.get("publication_status") == "PUBLISHED"
            and entry.get("is_test_fixture") is False
            and entry.get("review_status") == "HUMAN_APPROVED"
        )
    # DEVELOPMENT: published formal animations plus explicitly marked fixtures.
    if entry.get("is_test_fixture") and entry.get("publication_status") != "WITHDRAWN":
        return True
    return (
        entry.get("publication_status") == "PUBLISHED"
        and entry.get("review_status") == "HUMAN_APPROVED"
    )


async def _chapter_is_visible(
    db: AsyncSession, *, entry: dict[str, Any], viewer: ViewerScope
) -> bool:
    """The bound chapter must be readable under the frozen content rules."""

    from sqlalchemy import select

    from app.modules.content.models import Chapter, Course

    if viewer.stage is None:
        return False
    if entry.get("stage") != (
        viewer.stage.value if hasattr(viewer.stage, "value") else viewer.stage
    ):
        return False
    grade_min, grade_max = entry.get("grade_min"), entry.get("grade_max")
    if viewer.grade is not None and grade_min is not None and grade_max is not None:
        if not (grade_min <= viewer.grade <= grade_max):
            return False
    chapter_id = await db.scalar(
        select(Chapter.id)
        .join(Course, Course.id == Chapter.course_id)
        .where(
            Course.stable_slug == entry.get("course_slug"),
            Chapter.stable_slug == entry.get("chapter_slug"),
        )
    )
    if chapter_id is None:
        return False
    detail = await visible_chapter_detail(db, chapter_id=chapter_id, viewer=viewer)
    if detail is None:
        return False
    return detail.revision == entry.get("chapter_revision")


async def visible_animations(db: AsyncSession, *, viewer: ViewerScope) -> list[dict[str, Any]]:
    """Server-side filtered catalogue: the only source of animation ids."""

    if viewer.stage is None:
        return []
    visible: list[dict[str, Any]] = []
    for entry in load_definitions():
        if not _declaration_allows(entry, viewer):
            continue
        if not await _chapter_is_visible(db, entry=entry, viewer=viewer):
            continue
        visible.append(entry)
    return visible


async def load_visible_animation(
    db: AsyncSession, *, viewer: ViewerScope, identifier: str
) -> dict[str, Any]:
    for entry in await visible_animations(db, viewer=viewer):
        if entry["id"] == identifier:
            return entry
    raise AnimationNotVisible()


# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #
def _reject(code: str, message: str) -> None:
    raise AnimationParamsRejected(code, message)


def validate_params(entry: dict[str, Any], params: Any) -> dict[str, Any]:
    """Strict, bounded validation. Returns the normalised parameter object."""

    schema = entry["param_schema"]
    properties: dict[str, dict[str, Any]] = schema["properties"]
    limits = entry.get("limits", DEFAULT_LIMITS)
    # No parameters at all (null or {}) means "use the registered defaults";
    # defaults are part of the controlled definition, never client input.
    if params is None or params == {}:
        params = entry.get("defaults", {})
    if not isinstance(params, dict):
        _reject("ANIMATION_PARAMS_INVALID", "参数必须是对象")
    unknown = [key for key in params if key not in properties]
    if unknown:
        _reject("ANIMATION_PARAMS_UNKNOWN_KEY", f"不支持的参数：{', '.join(sorted(unknown))}")
    missing = [key for key in schema["required"] if key not in params]
    if missing:
        _reject("ANIMATION_PARAMS_MISSING", f"缺少参数：{', '.join(sorted(missing))}")

    normalised: dict[str, Any] = {}
    for key, spec in properties.items():
        if key not in params:
            continue
        value = params[key]
        if spec["type"] == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                _reject("ANIMATION_PARAMS_TYPE", f"参数 {key} 必须是整数")
            low = max(int(spec.get("min_value", limits["min_value"])), limits["min_value"])
            high = min(int(spec.get("max_value", limits["max_value"])), limits["max_value"])
            if not (low <= value <= high):
                _reject("ANIMATION_PARAMS_RANGE", f"参数 {key} 超出允许范围 {low}~{high}")
            normalised[key] = value
        else:
            if not isinstance(value, list) or any(
                isinstance(item, bool) or not isinstance(item, int) for item in value
            ):
                _reject("ANIMATION_PARAMS_TYPE", f"参数 {key} 必须是整数数组")
            max_items = min(int(spec.get("max_items", limits["max_items"])), limits["max_items"])
            min_items = max(int(spec.get("min_items", 0)), 0)
            if len(value) < min_items:
                _reject("ANIMATION_PARAMS_TOO_SHORT", f"参数 {key} 至少需要 {min_items} 个元素")
            if len(value) > max_items:
                _reject(
                    "ANIMATION_PARAMS_TOO_LONG",
                    f"参数 {key} 最多 {max_items} 个元素（收到 {len(value)} 个）",
                )
            low = max(int(spec.get("min_value", limits["min_value"])), limits["min_value"])
            high = min(int(spec.get("max_value", limits["max_value"])), limits["max_value"])
            for item in value:
                if not (low <= item <= high):
                    _reject("ANIMATION_PARAMS_RANGE", f"参数 {key} 的元素必须在 {low}~{high} 之间")
            normalised[key] = list(value)
    return normalised


def public_definition(entry: dict[str, Any]) -> dict[str, Any]:
    """The client payload: no filesystem paths, no executable content."""

    return {
        "id": entry["id"],
        "template": entry["template"],
        "title": entry["title"],
        "summary": entry.get("summary", ""),
        "stage": entry["stage"],
        "grade_min": entry.get("grade_min"),
        "grade_max": entry.get("grade_max"),
        "course_slug": entry.get("course_slug"),
        "chapter_slug": entry.get("chapter_slug"),
        "chapter_revision": entry.get("chapter_revision"),
        "knowledge_points": list(entry.get("knowledge_points") or []),
        "objectives": list(entry.get("objectives") or []),
        "preconditions": list(entry.get("preconditions") or []),
        "text_alternative": entry.get("text_alternative", ""),
        "param_schema": entry["param_schema"],
        "defaults": entry.get("defaults", {}),
        "limits": entry.get("limits", DEFAULT_LIMITS),
        "review_status": entry.get("review_status"),
        "publication_status": entry.get("publication_status"),
        "license_code": entry.get("license_code"),
        "is_test_fixture": bool(entry.get("is_test_fixture")),
        "content_notice": FIXTURE_NOTICE if entry.get("is_test_fixture") else None,
    }


async def animation_spec(
    db: AsyncSession, *, viewer: ViewerScope, identifier: str, params: Any
) -> dict[str, Any]:
    """Authorised definition + validated parameters; code never leaves here."""

    entry = await load_visible_animation(db, viewer=viewer, identifier=identifier)
    normalised = validate_params(entry, params)
    return {
        "definition": public_definition(entry),
        "params": normalised,
        "step_source": "CLIENT_PURE_FUNCTION",
    }


__all__ = [
    "ALLOWED_TEMPLATES",
    "AnimationError",
    "AnimationNotVisible",
    "AnimationParamsRejected",
    "DEFINITIONS_PATH",
    "FIXTURE_NOTICE",
    "animation_spec",
    "find_definition",
    "load_definitions",
    "load_visible_animation",
    "public_definition",
    "validate_params",
    "visible_animations",
]
