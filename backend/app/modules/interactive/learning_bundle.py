"""Reproducible offline packages and idempotent import of four learning activities."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.content.models import Chapter, ChapterRevision, Course
from app.modules.identity.models import User
from app.modules.interactive.models import InteractiveFile, InteractiveRevision
from app.modules.interactive.package import Manifest, build_document, read_package
from app.modules.interactive.service import activate_version, upload_revision
from app.modules.resources.models import Resource, ResourceChapterLink
from app.modules.resources.schemas import ResourceCreateRequest
from app.modules.resources.service import create_resource, store_for

ROOT = Path(__file__).resolve().parents[4] / "curriculum/interactive/computing-ai-v1"


def package_bytes(
    folder: Path,
    *,
    manifest_override: dict | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> bytes:
    manifest = manifest_override or json.loads(
        (folder / "manifest.json").read_text(encoding="utf-8")
    )
    scenes = [
        {
            **scene,
            "text": next(
                (
                    prompt["text"]
                    for prompt in manifest["prompts"]
                    if prompt["scene_id"] == scene["id"] and prompt["trigger"] == "SCENE_ENTER"
                ),
                "",
            ),
        }
        for scene in manifest["scenes"]
    ]
    files = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode()
        if manifest_override is not None
        else (folder / "manifest.json").read_bytes(),
        "index.html": (folder / "index.html").read_bytes(),
        "assets/cover.svg": (folder / "cover.svg").read_bytes(),
        "assets/style.css": (folder.parent / "shared/style.css").read_bytes(),
        "assets/bootstrap.js": (folder.parent / "shared/bootstrap.js").read_bytes(),
        "assets/activity.js": (
            "window.LESSON_SCENES="
            + json.dumps(scenes, ensure_ascii=False).replace("</", "<\\/")
            + ";\n"
            + (folder / "activity.js").read_text(encoding="utf-8")
        ).encode("utf-8"),
    }
    files.update(extra_files or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 30, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()


async def import_learning_activities(
    db: AsyncSession,
    *,
    actor: User,
    settings: Settings,
    root: Path = ROOT,
    upgrade_from: Path | None = None,
) -> dict[str, int]:
    if settings.app_env == "production":
        raise ValueError("Local learning activities must be imported in development/test")
    items = json.loads((root / "catalog.json").read_text(encoding="utf-8"))["items"]
    result = {
        "resources_created": 0,
        "versions_created": 0,
        "versions_reused": 0,
        "files_restored": 0,
    }
    for item in items:
        folder = root / item["folder"]
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        chapter = await db.scalar(
            select(ChapterRevision)
            .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
            .join(Course, Course.id == Chapter.course_id)
            .where(
                Course.stable_slug == item["course_slug"],
                Chapter.stable_slug == item["chapter_slug"],
                ChapterRevision.stage == item["stage"],
            )
            .order_by(ChapterRevision.revision.desc())
            .limit(1)
        )
        if chapter is None:
            raise ValueError(f"Import the related course first: {item['course_slug']}")
        resource = await db.scalar(
            select(Resource).where(Resource.stable_slug == manifest["content_key"])
        )
        if resource is None:
            resource = await create_resource(
                db,
                actor=actor,
                payload=ResourceCreateRequest(
                    slug=manifest["content_key"],
                    title=manifest["title"],
                    description=manifest["summary"],
                    kind="INTERACTIVE",
                    stage=item["stage"],
                    grade_min=chapter.grade_min,
                    grade_max=chapter.grade_max,
                    interactive_purpose=manifest["purpose"],
                    interactive_subject=manifest["subject"],
                    source_kind="NEW_SOURCE",
                    source_note="霜铃项目编写的 HTML 互动知识讲解；台词依据本地学习讲义整理。",
                    license_code="PROJECT-ORIGINAL",
                    local_demo_visible=True,
                    chapter_revision_ids=[chapter.id],
                ),
            )
            result["resources_created"] += 1
        elif (
            resource.kind != "INTERACTIVE"
            or resource.stage != item["stage"]
            or not resource.local_demo_visible
        ):
            raise ValueError("Learning content key conflicts with an existing resource")
        linked = await db.scalar(
            select(ResourceChapterLink.id).where(
                ResourceChapterLink.resource_id == resource.id,
                ResourceChapterLink.chapter_revision_id == chapter.id,
            )
        )
        if linked is None:
            db.add(ResourceChapterLink(resource_id=resource.id, chapter_revision_id=chapter.id))
            await db.commit()
        expected_active = resource.active_interactive_revision_id
        raw = package_bytes(folder)
        if upgrade_from is None and expected_active:
            active = await db.get(InteractiveRevision, expected_active)
            if await uses_current_template(db, active=active, folder=folder, settings=settings):
                result["versions_reused"] += 1
                continue
        if upgrade_from is not None and expected_active:
            active = await db.get(InteractiveRevision, expected_active)
            upgraded = await preserved_upgrade_package(
                db,
                active=active,
                folder=folder,
                previous_folder=upgrade_from / item["folder"],
                settings=settings,
            )
            if upgraded is None:
                result["versions_skipped"] = result.get("versions_skipped", 0) + 1
                continue
            raw = upgraded
        digest = hashlib.sha256(raw).hexdigest()
        existing = await db.scalar(
            select(InteractiveRevision).where(
                InteractiveRevision.resource_id == resource.id,
                InteractiveRevision.package_sha256 == digest,
            )
        )
        if existing is not None:
            result["files_restored"] += await restore_known_files(
                db, revision=existing, raw=raw, settings=settings
            )
            result["versions_reused"] += 1
            if upgrade_from is not None and existing.id != expected_active:
                await activate_version(
                    db,
                    resource_id=resource.id,
                    revision_id=existing.id,
                    settings=settings,
                    expected_current_id=expected_active,
                )
            continue
        version = await upload_revision(
            db,
            resource_id=resource.id,
            actor=actor,
            raw=raw,
            filename=f"{item['folder']}.zip",
            settings=settings,
        )
        import uuid

        await activate_version(
            db,
            resource_id=resource.id,
            revision_id=uuid.UUID(version["id"]),
            settings=settings,
            **({"expected_current_id": expected_active} if upgrade_from is not None else {}),
        )
        result["versions_created"] += 1
    return result


async def uses_current_template(
    db: AsyncSession, *, active: InteractiveRevision, folder: Path, settings: Settings
) -> bool:
    """A normal setup must not replace an already-upgraded, edited active version."""
    store = store_for(settings)
    if not store.exists(active.document_storage_key):
        return False
    with zipfile.ZipFile(io.BytesIO(package_bytes(folder))) as archive:
        expected = {name: archive.read(name) for name in archive.namelist()}
    assets = {
        asset.relative_path: asset
        for asset in await db.scalars(
            select(InteractiveFile).where(InteractiveFile.revision_id == active.id)
        )
    }
    for name in ("index.html", "assets/style.css", "assets/bootstrap.js"):
        if name not in assets or assets[name].sha256 != hashlib.sha256(expected[name]).hexdigest():
            return False
    activity = assets.get("assets/activity.js")
    if activity is None or not store.exists(activity.storage_key):
        return False
    raw = store.resolve(activity.storage_key).read_bytes()
    if hashlib.sha256(raw).hexdigest() != activity.sha256:
        return False
    prefix, separator, authored = raw.partition(b"\n")
    try:
        if not prefix.startswith(b"window.LESSON_SCENES=") or not prefix.endswith(b";"):
            return False
        scenes = json.loads(prefix[len(b"window.LESSON_SCENES=") : -1])
        if not isinstance(scenes, list):
            return False
    except (ValueError, UnicodeDecodeError):
        return False
    return bool(separator) and authored == (folder / "activity.js").read_text().encode("utf-8")


async def preserved_upgrade_package(
    db: AsyncSession,
    *,
    active: InteractiveRevision,
    folder: Path,
    previous_folder: Path,
    settings: Settings,
) -> bytes | None:
    """Only upgrade known authored assets. Keep all current metadata and audio."""
    new_manifest = json.loads((folder / "manifest.json").read_text())
    prior = active.manifest
    if (
        prior.get("content_key") != new_manifest["content_key"]
        or {scene["id"] for scene in prior["scenes"]}
        != {scene["id"] for scene in new_manifest["scenes"]}
        or {(p["id"], p["scene_id"]) for p in prior["prompts"]}
        != {(p["id"], p["scene_id"]) for p in new_manifest["prompts"]}
        or set(prior.get("capabilities", [])) != set(new_manifest["capabilities"])
    ):
        return None
    with zipfile.ZipFile(io.BytesIO(package_bytes(previous_folder))) as archive:
        previous = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(io.BytesIO(package_bytes(folder, manifest_override=prior))) as archive:
        current = {name: archive.read(name) for name in archive.namelist()}
    assets = {
        asset.relative_path: asset
        for asset in await db.scalars(
            select(InteractiveFile).where(InteractiveFile.revision_id == active.id)
        )
    }
    controlled = [prior["entry"], "assets/style.css", "assets/bootstrap.js", "assets/activity.js"]
    for name in controlled:
        asset = assets.get(name)
        if asset is None or asset.sha256 not in {
            hashlib.sha256(source[name]).hexdigest()
            for source in (previous, current)
            if name in source
        }:
            return None
    store = store_for(settings)
    additional = {}
    for name in {p.get("audio") for p in prior["prompts"]} | {prior.get("cover")}:
        if name:
            if name in {*controlled, "manifest.json"}:
                return None
            asset = assets.get(name)
            if asset is None or not store.exists(asset.storage_key):
                return None
            additional[name] = store.resolve(asset.storage_key).read_bytes()
    return package_bytes(folder, manifest_override=deepcopy(prior), extra_files=additional)


async def restore_known_files(
    db: AsyncSession, *, revision: InteractiveRevision, raw: bytes, settings: Settings
) -> int:
    """Recover missing bytes from a hash-identical repository package, never replace files."""
    store = store_for(settings)
    assets = list(
        await db.scalars(select(InteractiveFile).where(InteractiveFile.revision_id == revision.id))
    )
    missing = [asset for asset in assets if not store.exists(asset.storage_key)]
    if (
        not missing
        and store.exists(revision.document_storage_key)
        and store.exists(revision.package_storage_key)
    ):
        return 0
    if hashlib.sha256(raw).hexdigest() != revision.package_sha256:
        raise ValueError("The recovery package does not match the stored version")
    files, _ = read_package(
        raw,
        "recovery.zip",
        default={"stage": revision.manifest["stage"], "purpose": revision.manifest["purpose"]},
    )
    for asset in missing:
        if (
            asset.relative_path not in files
            or hashlib.sha256(files[asset.relative_path]).hexdigest() != asset.sha256
        ):
            raise ValueError("A custom asset cannot be recovered from the repository package")
    writes = [(asset.storage_key, files[asset.relative_path]) for asset in missing]
    if not store.exists(revision.package_storage_key):
        writes.append((revision.package_storage_key, raw))
    if not store.exists(revision.document_storage_key):
        bridge = Path(__file__).with_name("bridge.js").read_text(encoding="utf-8")
        document = build_document(files, Manifest.model_validate(revision.manifest), bridge)
        writes.append((revision.document_storage_key, document.encode("utf-8")))
    for key, data in writes:
        store.write_stream(key, io.BytesIO(data), max_bytes=110 * 1024 * 1024)
    return len(writes)
