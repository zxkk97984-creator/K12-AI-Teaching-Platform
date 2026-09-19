"""Deterministic local lesson-package renderer (T22 V2).

The Designer returns a *structured spec* that already validated against the
frozen ``k12.lesson.package.draft.v1`` schema. This renderer turns that spec
into **real files** on disk — deterministically (same spec ⇒ byte-identical
output) and without any template engine, HTML or script execution:

* ``lesson.md``    — the human-readable lesson (review/preview surface);
* ``package.json`` — the canonical structured manifest (spec-derived content,
  referenced animation definitions with validated parameters, source refs).

``asset_request`` entries are explicitly **not** rendered: they ask a human to
supply artwork/video. A package that only holds asset requests therefore has no
artefact and can never be approved or published.

The manifest deliberately carries no package id: identity lives in the database
and the bundle path, so the *content* bytes depend only on the spec.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.modules.authoring.material import registry_definition_for
from app.modules.resources.animation_service import (
    AnimationError,
    validate_params,
)

RENDERER_ID = "LOCAL_DETERMINISTIC_V1"


class RenderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RenderedFile:
    kind: str
    storage_key: str
    filename: str
    mime: str
    size_bytes: int
    sha256: str


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": "))


def _safe_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)
    return cleaned.strip("-")[:60] or "package"


def _lesson_markdown(spec: dict[str, Any], *, chapter_revision_id: str) -> str:
    lines: list[str] = []
    lines.append(f"# {spec.get('title', '（未命名课时）')}")
    lines.append("")
    lines.append(f"- 章节版本：`{chapter_revision_id}`")
    lines.append(f"- 学段：`{spec.get('stage', 'UNKNOWN')}`")
    lines.append(
        f"- 来源：Designer `{spec.get('schema_version', 'unknown')}`（结构化草稿，非人工审校成品）"
    )
    lines.append("")
    lines.append("## 教学目标")
    for item in spec.get("objectives") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 讲解脚本")
    script = spec.get("teaching_script")
    if isinstance(script, str) and script.strip():
        lines.append(script.strip())
    else:  # pragma: no cover - schema requires a non-empty string
        lines.append("（空）")
    lines.append("")
    lines.append("## 活动")
    for index, activity in enumerate(spec.get("activities") or [], start=1):
        if isinstance(activity, dict):
            resource = activity.get("suggested_resource_id")
            suffix = f"（建议资源：`{resource}`）" if resource else ""
            kind = activity.get("kind", "ACTIVITY")
            instruction = activity.get("instruction", "")
            lines.append(f"{index}. [{kind}] {instruction}{suffix}")
        else:  # pragma: no cover - schema requires objects
            lines.append(f"{index}. {activity}")
    lines.append("")
    animations = spec.get("animation_specs") or []
    if animations:
        lines.append("## 动画引用（步骤由前端确定性函数生成）")
        for animation in animations:
            if isinstance(animation, dict):
                definition = registry_definition_for(str(animation.get("template", "")))
                definition_id = definition["id"] if definition is not None else "UNREGISTERED"
                lines.append(
                    f"- `{animation.get('template', '')}` → 动画定义 `{definition_id}`；"
                    f"参数 `{canonical_json(animation.get('values', []))}`"
                )
                narration = animation.get("narration")
                if isinstance(narration, str) and narration.strip():
                    lines.append(f"  旁白：{narration.strip()}")
        lines.append("")
    requests = spec.get("asset_requests") or []
    lines.append("## 待人工提供的素材（不是产物）")
    if requests:
        for request in requests:
            if isinstance(request, dict):
                lines.append(
                    f"- [{request.get('kind', 'ASSET')}] {request.get('description', '')}"
                    f"（需要人工提供，未生成）"
                )
    else:
        lines.append("- 无")
    warnings = spec.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("## 自动校验提醒")
        for warning in warnings:
            lines.append(f"- {warning}")
    lines.append("")
    return "\n".join(lines)


def _validate_animation_refs(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Only registered definitions with schema-valid parameters may be referenced."""

    checked: list[dict[str, Any]] = []
    for raw in spec.get("animation_specs") or []:
        if not isinstance(raw, dict):  # pragma: no cover - schema enforced
            raise RenderError("AUTHORING_ANIMATION_INVALID", "animation_specs 条目必须是对象")
        template = raw.get("template")
        definition = (
            registry_definition_for(template) if isinstance(template, str) and template else None
        )
        if definition is None:
            raise RenderError("AUTHORING_ANIMATION_UNKNOWN", f"未登记的动画模板：{template}")
        params: dict[str, Any] = {"values": raw.get("values")}
        if raw.get("target") is not None:
            params["target"] = raw.get("target")
        try:
            validated = validate_params(definition, params)
        except AnimationError as error:
            raise RenderError(error.code, error.message) from error
        checked.append(
            {
                "template": template,
                "animation_id": definition["id"],
                "params": validated,
                "narration": raw.get("narration", ""),
                "source_refs": raw.get("source_refs", []),
            }
        )
    return checked


def render_package(
    settings: Settings,
    *,
    package_id: str,
    chapter_revision_id: str,
    spec: dict[str, Any],
) -> list[RenderedFile]:
    """Write the real files and return their verified digests."""

    root = Path(settings.authoring_artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / _safe_segment(package_id)
    if folder.is_symlink():
        raise RenderError("AUTHORING_PATH_SYMLINK", "产物目录不能是符号链接")
    folder.mkdir(parents=True, exist_ok=True)
    resolved = folder.resolve()
    if root.resolve() not in resolved.parents and resolved != root.resolve():
        raise RenderError("AUTHORING_PATH_ESCAPE", "产物路径越界")

    animations = _validate_animation_refs(spec)
    manifest = {
        "schema_version": "k12.authoring.package-manifest.v1",
        "chapter_revision_id": chapter_revision_id,
        "renderer": RENDERER_ID,
        "title": spec.get("title", ""),
        "stage": spec.get("stage", ""),
        "objectives": spec.get("objectives", []),
        "teaching_script": spec.get("teaching_script", ""),
        "activities": spec.get("activities", []),
        "animation_refs": animations,
        "asset_requests": spec.get("asset_requests", []),
        "source_refs": spec.get("source_refs", []),
        "warnings": spec.get("warnings", []),
        "designer_spec_version": spec.get("schema_version"),
    }
    markdown = _lesson_markdown(spec, chapter_revision_id=chapter_revision_id)

    outputs = [
        ("LESSON_MARKDOWN", "lesson.md", "text/markdown", markdown),
        ("PACKAGE_MANIFEST", "package.json", "application/json", canonical_json(manifest) + "\n"),
    ]
    rendered: list[RenderedFile] = []
    for kind, filename, mime, content in outputs:
        target = folder / filename
        target.write_text(content, encoding="utf-8")
        # read back: only bytes that really exist on disk count as an artefact
        data = target.read_bytes()
        if not data:  # pragma: no cover - defensive
            raise RenderError("AUTHORING_EMPTY_ARTIFACT", f"{filename} 渲染为空")
        rendered.append(
            RenderedFile(
                kind=kind,
                storage_key=f"{_safe_segment(package_id)}/{filename}",
                filename=filename,
                mime=mime,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    return rendered


def verify_artifact(settings: Settings, *, storage_key: str, sha256: str, size_bytes: int) -> bool:
    """Re-read from disk and confirm size+digest. Missing/edited files fail."""

    root = Path(settings.authoring_artifact_root).resolve()
    candidate = (root / storage_key).resolve()
    if root not in candidate.parents:
        return False
    if not candidate.is_file():
        return False
    data = candidate.read_bytes()
    return len(data) == size_bytes and hashlib.sha256(data).hexdigest() == sha256


__all__ = [
    "RENDERER_ID",
    "RenderError",
    "RenderedFile",
    "canonical_json",
    "render_package",
    "verify_artifact",
]
