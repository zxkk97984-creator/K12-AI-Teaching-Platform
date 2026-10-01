"""Interactive package lifecycle, visibility and private activity persistence."""

from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.content.schemas import ViewerScope
from app.modules.identity.models import User
from app.modules.interactive.models import (
    InteractiveEvent,
    InteractiveFile,
    InteractiveRevision,
    InteractiveSession,
)
from app.modules.interactive.package import (
    Manifest,
    PackageError,
    build_document,
    file_digest,
    read_package,
)
from app.modules.resources.models import Resource, ResourceChapterLink
from app.modules.resources.service import (
    ResourceError,
    load_visible_resource,
    store_for,
    visibility_condition,
)


class InteractiveError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _data_hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _version_public(row: InteractiveRevision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "resource_id": str(row.resource_id),
        "revision": row.revision,
        "manifest": row.manifest,
        "capabilities": row.capabilities,
        "package_sha256": row.package_sha256,
        "validation_report": row.validation_report,
        "locked": row.locked_at is not None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _session_public(row: InteractiveSession) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "resource_id": str(row.resource_id),
        "revision_id": str(row.revision_id),
        "stage": row.stage,
        "status": row.status,
        "base_revision": row.base_revision,
        "current_scene_id": row.current_scene_id,
        "game_state": row.game_state,
        "host_state": row.host_state,
        "game_result": row.game_result,
        "completion_source": row.completion_source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


async def upload_revision(
    db: AsyncSession,
    *,
    resource_id: uuid.UUID,
    actor: User,
    raw: bytes,
    filename: str,
    settings: Settings,
) -> dict[str, Any]:
    resource = await db.scalar(select(Resource).where(Resource.id == resource_id).with_for_update())
    if resource is None or resource.kind != "INTERACTIVE":
        raise InteractiveError("INTERACTIVE_NOT_FOUND", "互动资源不存在", 404)
    if actor.role != "admin":
        raise InteractiveError("INTERACTIVE_FORBIDDEN", "仅管理员可导入互动内容", 403)
    defaults = {
        "slug": resource.stable_slug,
        "title": resource.title,
        "stage": resource.stage,
        "purpose": resource.interactive_purpose or "LESSON",
        "subject": resource.interactive_subject or "综合",
        "summary": resource.description,
    }
    try:
        files, manifest = read_package(raw, filename, default=defaults)
        bridge = (Path(__file__).with_name("bridge.js")).read_text(encoding="utf-8")
        document = build_document(files, manifest, bridge)
    except PackageError as caught:
        raise InteractiveError(caught.code, str(caught)) from caught
    number = (
        int(
            await db.scalar(
                select(func.max(InteractiveRevision.revision)).where(
                    InteractiveRevision.resource_id == resource.id
                )
            )
            or 0
        )
        + 1
    )
    if number == 1:
        collision = await db.scalar(
            select(Resource.id).where(
                Resource.stable_slug == manifest.content_key,
                Resource.id != resource.id,
            )
        )
        if collision is not None:
            raise InteractiveError(
                "INTERACTIVE_CONTENT_KEY_EXISTS", "内容标识已被其他资源使用", 409
            )
        resource.stable_slug = manifest.content_key
    elif manifest.content_key != resource.stable_slug:
        raise InteractiveError("INTERACTIVE_CONTENT_KEY_CHANGED", "新版本须沿用原内容标识", 409)
    version_id = uuid.uuid4()
    prefix = f"interactive/{resource.id.hex}/{version_id.hex}"
    store = store_for(settings)
    written: list[str] = []
    try:
        package_key = f"{prefix}/original.{filename.rsplit('.', 1)[-1].lower()}"
        document_key = f"{prefix}/document.html"
        store.write_stream(
            package_key, io.BytesIO(raw), max_bytes=settings.resource_upload_max_bytes
        )
        written.append(package_key)
        store.write_stream(
            document_key, io.BytesIO(document.encode("utf-8")), max_bytes=110 * 1024 * 1024
        )
        written.append(document_key)
        row = InteractiveRevision(
            id=version_id,
            resource_id=resource.id,
            revision=number,
            package_storage_key=package_key,
            package_sha256=file_digest(raw),
            document_storage_key=document_key,
            manifest=manifest.model_dump(mode="json"),
            capabilities=list(manifest.capabilities),
            validation_report={
                "status": "PASS",
                "scope": "STRUCTURE_AND_OFFLINE_ASSETS",
                "notes": [
                    "结构、路径和离线素材已校验；SDK 事件需在预览中实际操作验证",
                    "结构校验不代表教学审校",
                ],
            },
            created_by_user_id=actor.id,
        )
        db.add(row)
        await db.flush()
        for name, data in files.items():
            if not data:
                raise InteractiveError("INTERACTIVE_EMPTY_FILE", f"文件为空：{name}")
            digest = file_digest(data)
            suffix = Path(name).suffix.lower()
            key = f"{prefix}/files/{digest[:20]}{suffix}"
            store.write_stream(key, io.BytesIO(data), max_bytes=100 * 1024 * 1024)
            written.append(key)
            db.add(
                InteractiveFile(
                    revision_id=version_id,
                    relative_path=name,
                    storage_key=key,
                    mime_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                    size_bytes=len(data),
                    sha256=digest,
                )
            )
        if resource.active_interactive_revision_id is None:
            resource.active_interactive_revision_id = version_id
        await db.commit()
        await db.refresh(row)
        return _version_public(row)
    except IntegrityError as caught:
        await db.rollback()
        for key in dict.fromkeys(written):
            store.remove(key)
        raise InteractiveError(
            "INTERACTIVE_UPLOAD_CONFLICT", "内容标识或版本发生冲突，请刷新后重试", 409
        ) from caught
    except Exception:
        await db.rollback()
        for key in dict.fromkeys(written):
            store.remove(key)
        raise


async def list_versions(db: AsyncSession, *, resource_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = list(
        await db.scalars(
            select(InteractiveRevision)
            .where(InteractiveRevision.resource_id == resource_id)
            .order_by(InteractiveRevision.revision.desc())
        )
    )
    return [_version_public(row) for row in rows]


async def update_draft(
    db: AsyncSession,
    *,
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    manifest_data: dict[str, Any],
) -> dict[str, Any]:
    resource = await db.scalar(select(Resource).where(Resource.id == resource_id))
    row = await db.scalar(
        select(InteractiveRevision)
        .where(
            InteractiveRevision.id == revision_id, InteractiveRevision.resource_id == resource_id
        )
        .with_for_update()
    )
    if resource is None or row is None:
        raise InteractiveError("INTERACTIVE_NOT_FOUND", "版本不存在", 404)
    if row.locked_at:
        raise InteractiveError(
            "INTERACTIVE_VERSION_LOCKED", "已发布版本不可修改，请上传新版本", 409
        )
    try:
        manifest = Manifest.model_validate(manifest_data)
    except Exception as caught:
        raise InteractiveError("INTERACTIVE_MANIFEST_INVALID", "内容清单无效") from caught
    if manifest.stage != resource.stage or manifest.purpose != resource.interactive_purpose:
        raise InteractiveError("INTERACTIVE_STAGE_CONFLICT", "内容学段或用途与资源不一致")
    if manifest.content_key != resource.stable_slug:
        raise InteractiveError("INTERACTIVE_CONTENT_KEY_CHANGED", "内容标识不能修改")
    if manifest.entry != row.manifest.get("entry"):
        raise InteractiveError("INTERACTIVE_ENTRY_IMMUTABLE", "修改入口文件需要上传新版本")
    assets = {
        item.relative_path
        for item in await db.scalars(
            select(InteractiveFile).where(InteractiveFile.revision_id == row.id)
        )
    }
    if any(prompt.audio and prompt.audio not in assets for prompt in manifest.prompts):
        raise InteractiveError("INTERACTIVE_AUDIO_MISSING", "问题音频尚未上传")
    if manifest.cover and manifest.cover not in assets:
        raise InteractiveError("INTERACTIVE_COVER_MISSING", "封面素材不存在")
    row.manifest = manifest.model_dump(mode="json")
    row.capabilities = list(manifest.capabilities)
    await db.commit()
    await db.refresh(row)
    return _version_public(row)


async def clone_draft(
    db: AsyncSession,
    *,
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    actor: User,
    settings: Settings,
) -> dict[str, Any]:
    """Create an editable copy without changing any active or historical version."""
    revision = await db.scalar(
        select(InteractiveRevision).where(
            InteractiveRevision.id == revision_id,
            InteractiveRevision.resource_id == resource_id,
        )
    )
    if revision is None:
        raise InteractiveError("INTERACTIVE_NOT_FOUND", "版本不存在", 404)
    files = list(
        await db.scalars(select(InteractiveFile).where(InteractiveFile.revision_id == revision_id))
    )
    store = store_for(settings)
    if any(not store.exists(file.storage_key) for file in files):
        raise InteractiveError("INTERACTIVE_FILE_MISSING", "版本素材缺失，无法复制", 503)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            if file.relative_path != "manifest.json":
                archive.writestr(file.relative_path, store.resolve(file.storage_key).read_bytes())
        archive.writestr("manifest.json", json.dumps(revision.manifest, ensure_ascii=False))
    return await upload_revision(
        db,
        resource_id=resource_id,
        actor=actor,
        raw=output.getvalue(),
        filename="editable-copy.zip",
        settings=settings,
    )


async def activate_version(
    db: AsyncSession,
    *,
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    settings: Settings,
    expected_current_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    resource = await db.scalar(
        select(Resource)
        .where(Resource.id == resource_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    row = await db.scalar(
        select(InteractiveRevision).where(
            InteractiveRevision.id == revision_id, InteractiveRevision.resource_id == resource_id
        )
    )
    if resource is None or row is None or resource.kind != "INTERACTIVE":
        raise InteractiveError("INTERACTIVE_NOT_FOUND", "版本不存在", 404)
    if (
        expected_current_id is not None
        and resource.active_interactive_revision_id != expected_current_id
    ):
        raise InteractiveError(
            "INTERACTIVE_REVISION_CONFLICT", "当前版本已变化，升级包保留为草稿，请重新检查", 409
        )
    if not store_for(settings).exists(row.document_storage_key):
        raise InteractiveError("INTERACTIVE_FILE_MISSING", "播放文档缺失", 409)
    row.locked_at = row.locked_at or datetime.now(UTC)
    resource.active_interactive_revision_id = row.id
    await db.commit()
    await db.refresh(row)
    return _version_public(row)


async def add_prompt_audio(
    db: AsyncSession,
    *,
    resource_id: uuid.UUID,
    revision_id: uuid.UUID,
    prompt_id: str,
    filename: str,
    raw: bytes,
    settings: Settings,
) -> dict[str, Any]:
    row = await db.scalar(
        select(InteractiveRevision)
        .where(
            InteractiveRevision.id == revision_id, InteractiveRevision.resource_id == resource_id
        )
        .with_for_update()
    )
    if row is None:
        raise InteractiveError("INTERACTIVE_NOT_FOUND", "版本不存在", 404)
    if row.locked_at:
        raise InteractiveError("INTERACTIVE_VERSION_LOCKED", "已发布版本不可修改", 409)
    ext = Path(filename).suffix.lower()
    if ext not in {".mp3", ".ogg", ".wav"} or not raw or len(raw) > 5 * 1024 * 1024:
        raise InteractiveError("INTERACTIVE_AUDIO_INVALID", "请选择不超过 5 MB 的 MP3、OGG 或 WAV")
    signatures = {
        ".mp3": raw.startswith(b"ID3")
        or (len(raw) >= 2 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0),
        ".ogg": raw.startswith(b"OggS"),
        ".wav": raw.startswith(b"RIFF") and raw[8:12] == b"WAVE",
    }
    if not signatures[ext]:
        raise InteractiveError("INTERACTIVE_AUDIO_INVALID", "音频内容与文件类型不匹配")
    manifest = Manifest.model_validate(row.manifest)
    prompt = next((item for item in manifest.prompts if item.id == prompt_id), None)
    if prompt is None:
        raise InteractiveError("INTERACTIVE_PROMPT_NOT_FOUND", "预设问题不存在", 404)
    name = f"audio/{prompt_id}{ext}"
    if await db.scalar(
        select(InteractiveFile).where(
            InteractiveFile.revision_id == revision_id, InteractiveFile.relative_path == name
        )
    ):
        raise InteractiveError("INTERACTIVE_AUDIO_EXISTS", "音频已存在，请上传新版本", 409)
    key = f"interactive/{resource_id.hex}/{revision_id.hex}/files/{file_digest(raw)[:20]}{ext}"
    store = store_for(settings)
    store.write_stream(key, io.BytesIO(raw), max_bytes=5 * 1024 * 1024)
    try:
        db.add(
            InteractiveFile(
                revision_id=row.id,
                relative_path=name,
                storage_key=key,
                mime_type={".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav"}[ext],
                size_bytes=len(raw),
                sha256=file_digest(raw),
            )
        )
        prompt.audio = name
        row.manifest = manifest.model_dump(mode="json")
        await db.commit()
    except Exception:
        await db.rollback()
        store.remove(key)
        raise
    return _version_public(row)


async def visible_resource(
    db: AsyncSession, *, resource_id: uuid.UUID, viewer: ViewerScope, settings: Settings
) -> tuple[Resource, InteractiveRevision]:
    try:
        resource = await load_visible_resource(db, viewer=viewer, resource_id=resource_id)
    except ResourceError as caught:
        raise InteractiveError("INTERACTIVE_NOT_VISIBLE", "互动内容不可用", 404) from caught
    if resource.kind != "INTERACTIVE" or resource.active_interactive_revision_id is None:
        raise InteractiveError("INTERACTIVE_NOT_VISIBLE", "互动内容不可用", 404)
    revision = await db.scalar(
        select(InteractiveRevision).where(
            InteractiveRevision.id == resource.active_interactive_revision_id,
            InteractiveRevision.resource_id == resource.id,
        )
    )
    if revision is None or not store_for(settings).exists(revision.document_storage_key):
        raise InteractiveError("INTERACTIVE_FILE_MISSING", "互动文件不可用", 503)
    return resource, revision


async def catalog(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    owner_id: uuid.UUID,
    settings: Settings,
    purpose: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    condition = visibility_condition(viewer)
    if condition is None:
        return []
    rows = list(
        await db.scalars(
            select(Resource)
            .where(
                condition,
                Resource.kind == "INTERACTIVE",
                Resource.active_interactive_revision_id.is_not(None),
            )
            .order_by(Resource.created_at.desc())
        )
    )
    sessions = list(
        await db.scalars(
            select(InteractiveSession)
            .where(InteractiveSession.owner_user_id == owner_id)
            .order_by(InteractiveSession.created_at.desc())
        )
    )
    latest = {}
    for session in sessions:
        latest.setdefault(session.resource_id, session)
    items = []
    links: dict[uuid.UUID, list[str]] = {}
    if rows:
        for link in await db.scalars(
            select(ResourceChapterLink).where(
                ResourceChapterLink.resource_id.in_([row.id for row in rows])
            )
        ):
            links.setdefault(link.resource_id, []).append(str(link.chapter_revision_id))
    for resource in rows:
        if purpose and resource.interactive_purpose != purpose:
            continue
        version = await db.scalar(
            select(InteractiveRevision).where(
                InteractiveRevision.id == resource.active_interactive_revision_id
            )
        )
        if version is None or not store_for(settings).exists(version.document_storage_key):
            continue
        if (
            q
            and q.casefold()
            not in (
                f"{resource.title} {resource.description} {resource.interactive_subject} "
                f"{' '.join(version.manifest.get('knowledge_points', []))}"
            ).casefold()
        ):
            continue
        activity = latest.get(resource.id)
        items.append(
            {
                "id": str(resource.id),
                "title": resource.title,
                "description": resource.description,
                "purpose": resource.interactive_purpose,
                "subject": resource.interactive_subject,
                "stage": resource.stage,
                "grade_min": resource.grade_min,
                "grade_max": resource.grade_max,
                "knowledge_points": version.manifest.get("knowledge_points", []),
                "cover": version.manifest.get("cover"),
                "revision": version.revision,
                "capabilities": version.capabilities,
                "is_test_fixture": resource.is_test_fixture,
                "local_demo_visible": resource.local_demo_visible,
                "chapter_revision_ids": links.get(resource.id, []),
                "activity_status": activity.status if activity else "NOT_STARTED",
                "can_resume": bool(
                    activity
                    and activity.status == "ACTIVE"
                    and "CHECKPOINTS"
                    in (
                        await db.scalar(
                            select(InteractiveRevision.capabilities).where(
                                InteractiveRevision.id == activity.revision_id
                            )
                        )
                        or []
                    )
                    and activity.base_revision > 0
                ),
                "session_id": str(activity.id) if activity else None,
            }
        )
    return items


async def owned_session(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    viewer: ViewerScope,
    settings: Settings,
    active: bool = False,
) -> tuple[InteractiveSession, Resource, InteractiveRevision]:
    session = await db.scalar(
        select(InteractiveSession).where(
            InteractiveSession.id == session_id, InteractiveSession.owner_user_id == owner_id
        )
    )
    if session is None:
        raise InteractiveError("INTERACTIVE_SESSION_NOT_FOUND", "活动不存在", 404)
    resource, _current = await visible_resource(
        db, resource_id=session.resource_id, viewer=viewer, settings=settings
    )
    if session.stage != resource.stage:
        raise InteractiveError("INTERACTIVE_STAGE_CHANGED", "请切回活动所属学段", 409)
    if active and session.status != "ACTIVE":
        raise InteractiveError("INTERACTIVE_NOT_ACTIVE", "活动已经结束", 409)
    revision = await db.scalar(
        select(InteractiveRevision).where(
            InteractiveRevision.id == session.revision_id,
            InteractiveRevision.resource_id == resource.id,
        )
    )
    if revision is None:
        raise InteractiveError("INTERACTIVE_VERSION_MISSING", "活动版本不存在", 404)
    return session, resource, revision


async def start_session(
    db: AsyncSession,
    *,
    resource_id: uuid.UUID,
    owner_id: uuid.UUID,
    viewer: ViewerScope,
    settings: Settings,
    restart: bool = False,
) -> dict[str, Any]:
    resource, revision = await visible_resource(
        db, resource_id=resource_id, viewer=viewer, settings=settings
    )
    existing = await db.scalar(
        select(InteractiveSession)
        .where(
            InteractiveSession.owner_user_id == owner_id,
            InteractiveSession.resource_id == resource.id,
            InteractiveSession.status == "ACTIVE",
        )
        .with_for_update()
    )
    if existing and not restart:
        return _session_public(existing)
    if existing:
        existing.status = "ABANDONED"
    session = InteractiveSession(
        owner_user_id=owner_id,
        resource_id=resource.id,
        revision_id=revision.id,
        stage=resource.stage,
        status="ACTIVE",
        game_state={},
        host_state={},
    )
    db.add(session)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        race = await db.scalar(
            select(InteractiveSession).where(
                InteractiveSession.owner_user_id == owner_id,
                InteractiveSession.resource_id == resource.id,
                InteractiveSession.status == "ACTIVE",
            )
        )
        if race is None:
            raise
        return _session_public(race)
    await db.refresh(session)
    return _session_public(session)


async def save_event(
    db: AsyncSession,
    *,
    session: InteractiveSession,
    revision: InteractiveRevision,
    owner_id: uuid.UUID,
    event_id: str,
    base_revision: int,
    kind: str,
    game_state: dict[str, Any] | None = None,
    scene_id: str | None = None,
    game_result: dict[str, Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    body = {
        "base_revision": base_revision,
        "kind": kind,
        "game_state": game_state,
        "scene_id": scene_id,
        "game_result": game_result,
        "source": source,
    }
    digest = _data_hash(body)
    prior = await db.scalar(
        select(InteractiveEvent).where(
            InteractiveEvent.session_id == session.id, InteractiveEvent.client_event_id == event_id
        )
    )
    if prior is not None:
        if prior.request_hash != digest:
            raise InteractiveError(
                "INTERACTIVE_IDEMPOTENCY_CONFLICT", "同一事件编号对应不同操作", 409
            )
        return prior.receipt
    row = await db.scalar(
        select(InteractiveSession).where(InteractiveSession.id == session.id).with_for_update()
    )
    if row is None or row.owner_user_id != owner_id:
        raise InteractiveError("INTERACTIVE_SESSION_NOT_FOUND", "活动不存在", 404)
    # The first lookup can race a concurrent request; repeat it after acquiring
    # the session row lock so identical retries receive the committed receipt.
    prior = await db.scalar(
        select(InteractiveEvent).where(
            InteractiveEvent.session_id == session.id,
            InteractiveEvent.client_event_id == event_id,
        )
    )
    if prior is not None:
        if prior.request_hash != digest:
            raise InteractiveError(
                "INTERACTIVE_IDEMPOTENCY_CONFLICT", "同一事件编号对应不同操作", 409
            )
        return prior.receipt
    if row.status != "ACTIVE" or row.base_revision != base_revision:
        raise InteractiveError("INTERACTIVE_REVISION_CONFLICT", "活动已更新，请读取最新记录", 409)
    scene_ids = {item["id"] for item in revision.manifest.get("scenes", [])}
    if scene_id is not None and scene_id not in scene_ids:
        raise InteractiveError("INTERACTIVE_SCENE_UNKNOWN", "场景不存在")
    if (
        kind == "CHECKPOINT"
        and game_state is not None
        and "CHECKPOINTS" not in revision.capabilities
    ):
        raise InteractiveError("INTERACTIVE_CHECKPOINTS_DISABLED", "这个内容没有启用检查点")
    if kind == "COMPLETE":
        if source == "SDK_REPORTED" and "COMPLETION" not in revision.capabilities:
            raise InteractiveError("INTERACTIVE_COMPLETION_DISABLED", "这个内容没有启用完成事件")
        if source == "USER_CONFIRMED" and ("COMPLETION" in revision.capabilities or game_result):
            raise InteractiveError("INTERACTIVE_COMPLETION_INVALID", "不能用手动完成覆盖游戏结果")
    if game_state is not None:
        encoded = json.dumps(game_state, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise InteractiveError("INTERACTIVE_CHECKPOINT_TOO_LARGE", "检查点超过 64 KB", 413)
        row.game_state = game_state
    if scene_id is not None:
        row.current_scene_id = scene_id
    if kind == "COMPLETE":
        result = game_result or {}
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 4096:
            raise InteractiveError("INTERACTIVE_RESULT_TOO_LARGE", "游戏结果过大", 413)
        score = result.get("score")
        maximum = result.get("maxScore")
        if score is not None and (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or score < 0
            or score > 1_000_000
        ):
            raise InteractiveError("INTERACTIVE_RESULT_INVALID", "游戏分数无效")
        if maximum is not None and (
            not isinstance(maximum, (int, float))
            or isinstance(maximum, bool)
            or maximum < 0
            or maximum > 1_000_000
            or (score is not None and score > maximum)
        ):
            raise InteractiveError("INTERACTIVE_RESULT_INVALID", "游戏满分无效")
        row.game_result = result
        row.completion_source = source or "SDK_REPORTED"
        row.completed_at = datetime.now(UTC)
        row.status = "COMPLETED"
    row.base_revision += 1
    row.updated_at = datetime.now(UTC)
    receipt = _session_public(row)
    db.add(
        InteractiveEvent(
            session_id=row.id,
            owner_user_id=owner_id,
            client_event_id=event_id,
            event_type=kind,
            request_hash=digest,
            receipt=receipt,
        )
    )
    await db.commit()
    return receipt
