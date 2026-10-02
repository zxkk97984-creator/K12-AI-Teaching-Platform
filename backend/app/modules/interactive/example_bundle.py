"""Import the offline autoplay examples without replacing edited active versions."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.identity.models import User
from app.modules.interactive.learning_bundle import restore_known_files
from app.modules.interactive.models import InteractiveRevision
from app.modules.interactive.package import Manifest, build_document, read_package
from app.modules.interactive.service import _data_hash, activate_version, upload_revision
from app.modules.resources.models import Resource
from app.modules.resources.schemas import ResourceCreateRequest
from app.modules.resources.service import create_resource

GRADES = {"PRIMARY_LOWER": (1, 3), "PRIMARY_UPPER": (4, 6), "JUNIOR": (7, 9), "SENIOR": (10, 12)}
ROOT = Path(__file__).resolve().parents[4] / "k12-autoplay-examples-v1"


def load_examples(root: Path) -> list[tuple[Path, bytes, Manifest]]:
    """Validate every package before writing any resources or files."""
    root = root.resolve()
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, list) or len(catalog) != 12:
        raise ValueError("Expected twelve autoplay examples")
    packages = []
    keys: set[str] = set()
    counts = dict.fromkeys(GRADES, 0)
    bridge = Path(__file__).with_name("bridge.js").read_text(encoding="utf-8")
    for item in catalog:
        path = (root / item["package_zip"]).resolve()
        path.relative_to(root)
        raw = path.read_bytes()
        files, manifest = read_package(
            raw, path.name, default={"stage": item["stage"], "purpose": "LESSON"}
        )
        if (
            manifest.purpose != "LESSON"
            or manifest.stage != item["stage"]
            or manifest.title != item["title"]
            or manifest.content_key in keys
        ):
            raise ValueError("Autoplay example metadata mismatch or duplicate key")
        build_document(files, manifest, bridge)
        keys.add(manifest.content_key)
        counts[manifest.stage] += 1
        packages.append((path, raw, manifest))
    if any(count != 3 for count in counts.values()):
        raise ValueError("Expected three autoplay examples in each stage")
    return packages


async def import_autoplay_examples(
    db: AsyncSession,
    *,
    actor: User,
    settings: Settings,
    root: Path = ROOT,
    upgrade_from: Path | None = None,
) -> dict[str, int]:
    if settings.app_env not in {"development", "test"}:
        raise ValueError("Autoplay examples require development/test")
    packages = load_examples(root)
    previous = (
        {
            manifest.content_key: {
                "package_sha256": hashlib.sha256(raw).hexdigest(),
                "manifest_sha256": _data_hash(manifest.model_dump(mode="json")),
            }
            for _, raw, manifest in load_examples(upgrade_from)
        }
        if upgrade_from
        else json.loads(Path(__file__).with_name("autoplay_previous.json").read_text())
    )
    resources = {}
    for _, _, manifest in packages:
        resource = await db.scalar(
            select(Resource).where(Resource.stable_slug == manifest.content_key)
        )
        if resource and (
            resource.kind != "INTERACTIVE"
            or resource.stage != manifest.stage
            or resource.interactive_purpose != "LESSON"
            or not resource.local_demo_visible
        ):
            raise ValueError(f"Existing resource conflicts with example: {manifest.content_key}")
        resources[manifest.content_key] = resource
    result = {
        "resources_created": 0,
        "versions_created": 0,
        "versions_reused": 0,
        "versions_skipped": 0,
        "files_restored": 0,
    }
    for path, raw, manifest in packages:
        resource = resources[manifest.content_key]
        if resource is None:
            low, high = GRADES[manifest.stage]
            resource = await create_resource(
                db,
                actor=actor,
                payload=ResourceCreateRequest(
                    slug=manifest.content_key,
                    title=manifest.title,
                    description=manifest.summary,
                    kind="INTERACTIVE",
                    stage=manifest.stage,
                    grade_min=low,
                    grade_max=high,
                    interactive_purpose="LESSON",
                    interactive_subject=manifest.subject,
                    source_kind="NEW_SOURCE",
                    license_code="PROJECT-ORIGINAL",
                    local_demo_visible=True,
                    source_note=(
                        "霜铃自动播放 HTML 教学演示；AI 辅助编写，"
                        "包含合成数据和简化教学模型，未经人工教学审校。"
                    ),
                ),
            )
            result["resources_created"] += 1
        digest = hashlib.sha256(raw).hexdigest()
        active = (
            await db.get(InteractiveRevision, resource.active_interactive_revision_id)
            if resource.active_interactive_revision_id
            else None
        )
        known_prior = previous.get(manifest.content_key, {})
        safe_upgrade = bool(
            active
            and known_prior.get("package_sha256") == active.package_sha256
            and known_prior.get("manifest_sha256") == _data_hash(active.manifest)
        )
        if active:
            if active.package_sha256 == digest:
                result["files_restored"] += await restore_known_files(
                    db, revision=active, raw=raw, settings=settings
                )
                result["versions_reused"] += 1
            elif not safe_upgrade:
                result["versions_skipped"] += 1
            if active.package_sha256 == digest or not safe_upgrade:
                continue
        existing = await db.scalar(
            select(InteractiveRevision).where(
                InteractiveRevision.resource_id == resource.id,
                InteractiveRevision.package_sha256 == digest,
            )
        )
        if existing:
            revision_id = existing.id
            result["files_restored"] += await restore_known_files(
                db, revision=existing, raw=raw, settings=settings
            )
            result["versions_reused"] += 1
        else:
            version = await upload_revision(
                db,
                resource_id=resource.id,
                actor=actor,
                raw=raw,
                filename=path.name,
                settings=settings,
            )
            revision_id = uuid.UUID(version["id"])
            result["versions_created"] += 1
        await activate_version(
            db,
            resource_id=resource.id,
            revision_id=revision_id,
            settings=settings,
            expected_current_id=active.id if active else None,
        )
    return result
