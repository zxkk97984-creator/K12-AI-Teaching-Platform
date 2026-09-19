"""Authoring export bundle: the published side of the closed loop (T22 V4).

Every publication appends an entry to ``<bundle_root>/index.json`` and writes an
immutable per-revision bundle file. The frozen
``platform/knodo/bundles/manifest.json`` (the shipped classroom bundle) is **not**
rewritten here: authoring products live in their own bundle root so a publish
cannot silently change what students already have. Old lessons keep their old
revision because the index is append-only and each entry is addressable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import Settings
from app.modules.authoring.renderer import canonical_json

INDEX_NAME = "index.json"


class BundleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def bundle_root(settings: Settings) -> Path:
    return Path(settings.authoring_bundle_root)


def _read_index(root: Path) -> dict[str, Any]:
    path = root / INDEX_NAME
    if not path.is_file():
        return {"schema_version": "k12.authoring.bundle-index.v1", "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:  # pragma: no cover - corrupt index
        raise BundleError("AUTHORING_BUNDLE_CORRUPT", "导出 bundle 索引损坏") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise BundleError("AUTHORING_BUNDLE_CORRUPT", "导出 bundle 索引结构无效")
    return payload


def publish_to_bundle(
    settings: Settings,
    *,
    package_id: str,
    package_revision: int,
    chapter_revision_id: str,
    artifact_sha256: str,
    title: str,
    published_by: str,
) -> str:
    """Append one immutable entry; returns the bundle-relative path."""

    root = bundle_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    index = _read_index(root)

    relative = f"packages/{package_id}-r{package_revision}.json"
    entry = {
        "package_id": package_id,
        "package_revision": package_revision,
        "chapter_revision_id": chapter_revision_id,
        "title": title,
        "artifact_sha256": artifact_sha256,
        "path": relative,
        "published_by": published_by,
    }
    payload = {
        "schema_version": "k12.authoring.bundle-entry.v1",
        **entry,
        "notice": "教研产物 bundle：只有 HUMAN_APPROVED 且含真实文件才会出现在这里。",
    }
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    (root / relative).write_text(canonical_json(payload) + "\n", encoding="utf-8")

    # append-only: re-publishing the same revision would be a bug, and the
    # unique (package, revision) constraint already forbids it.
    if not any(
        item.get("package_id") == package_id and item.get("package_revision") == package_revision
        for item in index["entries"]
        if isinstance(item, dict)
    ):
        index["entries"].append(entry)
    index["entries"].sort(
        key=lambda item: (item.get("package_id", ""), item.get("package_revision", 0))
    )
    index["content_sha256"] = hashlib.sha256(
        canonical_json(index["entries"]).encode("utf-8")
    ).hexdigest()
    (root / INDEX_NAME).write_text(canonical_json(index) + "\n", encoding="utf-8")
    return relative


__all__ = ["BundleError", "bundle_root", "publish_to_bundle"]
