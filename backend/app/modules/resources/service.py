"""Resource registry: registration, server-side filtering, safe delivery.

Permission truth lives here and only here:

* :func:`select_resource_candidates` and
  :func:`authorized_resource_ids_for_teaching` are the same filter used by the
  student API, the download endpoint and the Tutor's ``allowed_resource_ids``.
* :func:`allowed_resource_ids_for_teaching` is the pure, fail-closed gate the
  teaching context calls: nothing is authorized unless a server-side lookup
  proved it.
* Delivery re-checks visibility on every request, so a withdrawn or
  stage-mismatched resource cannot be reached through an old link, and the
  response is ``no-store`` so a cache cannot resurrect it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.storage import (
    LocalFileStore,
    StorageError,
    build_storage_key,
    sign_ticket,
    validate_upload,
    verify_ticket,
)
from app.core.storage.uploads import UploadRejected
from app.modules.content.models import (
    ChapterRevision,
    ContentProfile,
    KnowledgePoint,
    PublicationStatus,
    ReviewStatus,
)
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import FIXTURE_NOTICE
from app.modules.identity.models import User
from app.modules.resources.models import (
    Resource,
    ResourceChapterLink,
    ResourceKnowledgePoint,
    ResourceVariant,
)
from app.modules.resources.schemas import (
    ResourceCreateRequest,
    ResourceListDTO,
    ResourcePatchRequest,
    ResourceSummaryDTO,
    ResourceTicketDTO,
    ResourceUploadReceipt,
    ResourceVariantDTO,
)

TICKET_NOTICE = "临时链接：仅本人当次会话可用，不是教材资源 ID"
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class ResourceError(Exception):
    """Domain failure that maps to a readable HTTP error."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ResourceNotVisible(ResourceError):
    def __init__(self, message: str = "资源不可用") -> None:
        super().__init__("RESOURCE_NOT_VISIBLE", message, 404)


class ResourceFileMissing(ResourceError):
    def __init__(self, message: str = "资源文件缺失，请联系管理员") -> None:
        super().__init__("RESOURCE_FILE_MISSING", message, 404)


class ResourceStateError(ResourceError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


def store_for(settings: Settings) -> LocalFileStore:
    return LocalFileStore(Path(settings.resource_storage_root))


# --------------------------------------------------------------------------- #
# visibility: the one server-side permission filter
# --------------------------------------------------------------------------- #
def visibility_condition(viewer: ViewerScope):
    """SQL predicate for one viewer, or ``None`` when nothing may be read."""

    if viewer.stage is None:
        return None
    stage = viewer.stage.value if hasattr(viewer.stage, "value") else str(viewer.stage)
    published = and_(
        Resource.stage == stage,
        Resource.is_test_fixture.is_(False),
        Resource.review_status == ReviewStatus.HUMAN_APPROVED.value,
        Resource.publication_status == PublicationStatus.PUBLISHED.value,
    )
    alternatives = [published]
    if viewer.profile is ContentProfile.DEVELOPMENT:
        # Explicitly marked synthetic fixtures (dev/test only). They can never
        # be PUBLISHED (DB trigger) and are always labelled in the response.
        alternatives.append(
            and_(
                Resource.stage == stage,
                Resource.is_test_fixture.is_(True),
                Resource.publication_status != PublicationStatus.WITHDRAWN.value,
            )
        )
    condition = or_(*alternatives)
    if viewer.grade is not None:
        condition = and_(
            condition,
            or_(
                and_(Resource.grade_min.is_(None), Resource.grade_max.is_(None)),
                and_(
                    Resource.grade_min <= viewer.grade,
                    Resource.grade_max >= viewer.grade,
                ),
            ),
        )
    return condition


async def _linked_revision_ids(db: AsyncSession, resource_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(ResourceChapterLink.chapter_revision_id).where(
            ResourceChapterLink.resource_id == resource_id
        )
    )
    return list(rows)


async def _linked_knowledge_slugs(db: AsyncSession, resource_id: uuid.UUID) -> list[str]:
    rows = await db.scalars(
        select(KnowledgePoint.stable_slug)
        .join(
            ResourceKnowledgePoint, ResourceKnowledgePoint.knowledge_point_id == KnowledgePoint.id
        )
        .where(ResourceKnowledgePoint.resource_id == resource_id)
        .order_by(KnowledgePoint.stable_slug)
    )
    return list(rows)


async def _variants(db: AsyncSession, resource_id: uuid.UUID) -> list[ResourceVariant]:
    rows = await db.scalars(
        select(ResourceVariant)
        .where(ResourceVariant.resource_id == resource_id)
        .order_by(ResourceVariant.variant)
    )
    return list(rows)


def _variant_dto(variant: ResourceVariant, *, available: bool) -> ResourceVariantDTO:
    return ResourceVariantDTO(
        variant=variant.variant,  # type: ignore[arg-type]
        filename=variant.original_filename,
        mime=variant.detected_mime,
        size_bytes=variant.size_bytes,
        sha256=variant.sha256,
        inline_ok=_inline_ok(variant.detected_mime),
        available=available,
        unavailable_reason=None if available else "RESOURCE_FILE_MISSING",
    )


def _inline_ok(mime: str) -> bool:
    return mime.startswith(("video/", "image/")) or mime == "application/pdf"


async def _summary(
    db: AsyncSession, resource: Resource, *, settings: Settings | None = None
) -> ResourceSummaryDTO:
    return ResourceSummaryDTO(
        id=resource.id,
        slug=resource.stable_slug,
        title=resource.title,
        description=resource.description,
        kind=resource.kind,  # type: ignore[arg-type]
        interactive_purpose=resource.interactive_purpose,  # type: ignore[arg-type]
        interactive_subject=resource.interactive_subject,
        active_interactive_revision_id=resource.active_interactive_revision_id,
        stage=resource.stage,
        grade_min=resource.grade_min,
        grade_max=resource.grade_max,
        source_kind=resource.source_kind,
        source_note=resource.source_note,
        license_code=resource.license_code,
        license_note=resource.license_note,
        review_status=resource.review_status,
        publication_status=resource.publication_status,
        is_test_fixture=resource.is_test_fixture,
        content_notice=FIXTURE_NOTICE if resource.is_test_fixture else None,
        chapter_revision_ids=await _linked_revision_ids(db, resource.id),
        knowledge_point_slugs=await _linked_knowledge_slugs(db, resource.id),
        variants=[
            _variant_dto(item, available=_variant_available(item, settings))
            for item in await _variants(db, resource.id)
        ],
    )


def _variant_available(variant: ResourceVariant, settings: Settings | None) -> bool:
    """A row is not proof of bytes: the file must exist in the store."""

    if settings is None:
        return True
    return store_for(settings).exists(variant.storage_key)


async def select_resource_candidates(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    chapter_revision_id: uuid.UUID | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list[Resource]:
    """Server-side filtered candidate set: the only way a resource is offered."""

    condition = visibility_condition(viewer)
    if condition is None:
        return []
    statement = select(Resource).where(condition)
    if chapter_revision_id is not None:
        statement = statement.where(
            Resource.id.in_(
                select(ResourceChapterLink.resource_id).where(
                    ResourceChapterLink.chapter_revision_id == chapter_revision_id
                )
            )
        )
    if kind is not None:
        statement = statement.where(Resource.kind == kind)
    rows = await db.scalars(statement.order_by(Resource.title).limit(max(1, min(limit, 200))))
    return list(rows)


async def list_student_resources(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    chapter_revision_id: uuid.UUID | None = None,
    kind: str | None = None,
    settings: Settings | None = None,
    limit: int = 50,
) -> ResourceListDTO:
    candidates = await select_resource_candidates(
        db,
        viewer=viewer,
        chapter_revision_id=chapter_revision_id,
        kind=kind,
        limit=limit,
    )
    items = [await _summary(db, resource, settings=settings) for resource in candidates]
    items = [
        item
        for item in items
        if item.variants or (item.kind == "INTERACTIVE" and item.active_interactive_revision_id)
    ]
    profile = viewer.profile.value if hasattr(viewer.profile, "value") else str(viewer.profile)
    return ResourceListDTO(items=items, profile=profile)


async def load_visible_resource(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    resource_id: uuid.UUID,
) -> Resource:
    """Re-check visibility for one resource; raise ``ResourceNotVisible``."""

    condition = visibility_condition(viewer)
    if condition is None:
        raise ResourceNotVisible()
    resource = await db.scalar(select(Resource).where(Resource.id == resource_id, condition))
    if resource is None:
        raise ResourceNotVisible()
    return resource


async def resource_detail(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    resource_id: uuid.UUID,
    settings: Settings | None = None,
) -> ResourceSummaryDTO:
    resource = await load_visible_resource(db, viewer=viewer, resource_id=resource_id)
    if resource.kind == "INTERACTIVE" and resource.active_interactive_revision_id is not None:
        return await _summary(db, resource, settings=settings)
    if not await _variants(db, resource.id):
        # No file was ever registered: never advertise a ready resource.
        raise ResourceFileMissing("资源文件未登记")
    return await _summary(db, resource, settings=settings)


# --------------------------------------------------------------------------- #
# Tutor-facing authorization (R7)
# --------------------------------------------------------------------------- #
def allowed_resource_ids_for_teaching(
    *, authorized_ids: Sequence[str] | None, limit: int = 16
) -> list[str]:
    """Pure fail-closed gate used by the teaching context.

    ``authorized_ids`` must come from
    :func:`authorized_resource_ids_for_teaching` (a server-side lookup over the
    resource registry). Without it, nothing is authorized: no resource id, no
    clickable action. Shape checks drop anything that is not a resource id, so
    a model or a caller cannot smuggle in a URL, a temporary ticket or
    traversal text.
    """

    if authorized_ids is None:
        return []
    allowed: list[str] = []
    for raw in authorized_ids:
        text = str(raw)
        if not _UUID_RE.match(text):
            continue
        if text not in allowed:
            allowed.append(text)
        if len(allowed) >= max(1, limit):
            break
    return allowed


async def authorized_resource_ids_for_teaching(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    revision_id: uuid.UUID,
    limit: int = 16,
) -> list[str]:
    """DB-backed authorization: published, in-stage, linked to this revision."""

    candidates = await select_resource_candidates(
        db, viewer=viewer, chapter_revision_id=revision_id, limit=limit
    )
    authorized: list[str] = []
    for resource in candidates:
        if not await _variants(db, resource.id):
            # A registry row without a real stored file is never offered.
            continue
        authorized.append(str(resource.id))
    return authorized


# --------------------------------------------------------------------------- #
# admin: registration and state transitions
# --------------------------------------------------------------------------- #
def _validate_grade_pair(stage: str, grade_min: int | None, grade_max: int | None) -> None:
    if (grade_min is None) != (grade_max is None):
        raise ResourceError("RESOURCE_GRADE_PAIR", "年级区间必须同时提供或同时省略")
    if grade_min is None:
        return
    bounds = {
        "PRIMARY_LOWER": (1, 3),
        "PRIMARY_UPPER": (4, 6),
        "JUNIOR": (7, 9),
        "SENIOR": (10, 12),
    }[stage]
    assert grade_max is not None
    if grade_min > grade_max or grade_min < bounds[0] or grade_max > bounds[1]:
        raise ResourceError("RESOURCE_GRADE_RANGE", "年级区间与学段不一致")


async def _replace_links(
    db: AsyncSession, *, resource: Resource, revision_ids: Sequence[uuid.UUID]
) -> None:
    await db.execute(
        ResourceChapterLink.__table__.delete().where(ResourceChapterLink.resource_id == resource.id)
    )
    for revision_id in dict.fromkeys(revision_ids):
        revision = await db.scalar(select(ChapterRevision).where(ChapterRevision.id == revision_id))
        if revision is None:
            raise ResourceError("RESOURCE_REVISION_UNKNOWN", "章节版本不存在", 404)
        if revision.stage != resource.stage:
            raise ResourceError("RESOURCE_REVISION_STAGE", "章节版本与资源学段不一致", 409)
        db.add(ResourceChapterLink(resource_id=resource.id, chapter_revision_id=revision_id))


async def _replace_knowledge_points(
    db: AsyncSession, *, resource: Resource, slugs: Sequence[str]
) -> None:
    await db.execute(
        ResourceKnowledgePoint.__table__.delete().where(
            ResourceKnowledgePoint.resource_id == resource.id
        )
    )
    for slug in dict.fromkeys(slugs):
        point = await db.scalar(select(KnowledgePoint).where(KnowledgePoint.stable_slug == slug))
        if point is None:
            raise ResourceError("RESOURCE_KNOWLEDGE_POINT_UNKNOWN", "知识点不存在", 404)
        db.add(ResourceKnowledgePoint(resource_id=resource.id, knowledge_point_id=point.id))


async def create_resource(
    db: AsyncSession, *, actor: User, payload: ResourceCreateRequest
) -> Resource:
    if actor.role != "admin":  # defence in depth; the router also enforces this
        raise ResourceError("RESOURCE_FORBIDDEN", "仅管理员可登记资源", 403)
    _validate_grade_pair(payload.stage, payload.grade_min, payload.grade_max)
    if payload.is_test_fixture != (payload.source_kind == "SYNTHETIC_FIXTURE"):
        raise ResourceError("RESOURCE_FIXTURE_FLAG", "合成夹具标记与来源类型必须一致", 422)
    if payload.kind == "INTERACTIVE":
        if not payload.interactive_purpose or not (payload.interactive_subject or "").strip():
            raise ResourceError("INTERACTIVE_METADATA_REQUIRED", "互动内容需要用途和学科", 422)
    elif payload.interactive_purpose or payload.interactive_subject:
        raise ResourceError("INTERACTIVE_METADATA_INVALID", "普通资源不能设置互动内容字段", 422)
    existing = await db.scalar(select(Resource).where(Resource.stable_slug == payload.slug))
    if existing is not None:
        raise ResourceError("RESOURCE_SLUG_TAKEN", "资源 slug 已存在", 409)
    resource = Resource(
        stable_slug=payload.slug,
        title=payload.title,
        description=payload.description,
        kind=payload.kind,
        interactive_purpose=payload.interactive_purpose,
        interactive_subject=payload.interactive_subject.strip()
        if payload.interactive_subject
        else None,
        stage=payload.stage,
        grade_min=payload.grade_min,
        grade_max=payload.grade_max,
        source_kind=payload.source_kind,
        source_note=payload.source_note,
        license_code=payload.license_code,
        license_note=payload.license_note,
        review_status="UNREVIEWED",
        publication_status="DRAFT",
        is_test_fixture=payload.is_test_fixture,
        uploaded_by_user_id=actor.id,
    )
    db.add(resource)
    await db.flush()
    await _replace_links(db, resource=resource, revision_ids=payload.chapter_revision_ids)
    await _replace_knowledge_points(db, resource=resource, slugs=payload.knowledge_point_slugs)
    await db.commit()
    await db.refresh(resource)
    return resource


async def patch_resource(
    db: AsyncSession,
    *,
    actor: User,
    resource: Resource,
    payload: ResourcePatchRequest,
    settings: Settings | None = None,
) -> Resource:
    if actor.role != "admin":
        raise ResourceError("RESOURCE_FORBIDDEN", "仅管理员可修改资源", 403)
    data = payload.model_dump(exclude_unset=True)
    chapter_revision_ids = data.pop("chapter_revision_ids", None)

    if "grade_min" in data or "grade_max" in data:
        grade_min = data.get("grade_min", resource.grade_min)
        grade_max = data.get("grade_max", resource.grade_max)
        _validate_grade_pair(resource.stage, grade_min, grade_max)
        resource.grade_min = grade_min
        resource.grade_max = grade_max

    for field in ("title", "description", "source_note", "license_code", "license_note"):
        if field in data and data[field] is not None:
            setattr(resource, field, data[field])

    review = data.get("review_status")
    if review is not None:
        if review == "HUMAN_APPROVED":
            # Only a real reviewer identity may approve; the actor is the
            # server-side session user, never a client-supplied field.
            resource.reviewer_id = actor.id
            resource.reviewed_at = datetime.now(UTC)
        resource.review_status = review

    publication = data.get("publication_status")
    if publication is not None:
        if publication == "PUBLISHED":
            if resource.is_test_fixture or resource.source_kind == "SYNTHETIC_FIXTURE":
                raise ResourceStateError(
                    "RESOURCE_FIXTURE_NOT_PUBLISHABLE", "合成测试资源不能发布为正式资源"
                )
            if resource.review_status != "HUMAN_APPROVED":
                raise ResourceStateError("RESOURCE_NOT_APPROVED", "资源未通过人工审校，不能发布")
            if resource.kind == "INTERACTIVE":
                from app.modules.interactive.models import InteractiveRevision

                revision = await db.scalar(
                    select(InteractiveRevision).where(
                        InteractiveRevision.id == resource.active_interactive_revision_id,
                        InteractiveRevision.resource_id == resource.id,
                    )
                )
                if revision is None:
                    raise ResourceStateError(
                        "INTERACTIVE_VERSION_MISSING", "请先上传并选择可运行版本"
                    )
                if settings is not None and not store_for(settings).exists(
                    revision.document_storage_key
                ):
                    raise ResourceStateError("INTERACTIVE_FILE_MISSING", "播放文档缺失，不能发布")
                revision.locked_at = revision.locked_at or datetime.now(UTC)
            elif not await _variants(db, resource.id):
                raise ResourceStateError("RESOURCE_FILE_MISSING", "资源还没有真实文件，不能发布")
        resource.publication_status = publication

    if chapter_revision_ids is not None:
        await _replace_links(db, resource=resource, revision_ids=chapter_revision_ids)

    await db.commit()
    await db.refresh(resource)
    return resource


async def stage_upload(
    store: LocalFileStore, chunks: Any, *, max_bytes: int
) -> tuple[Path, int, str]:
    """Stage a raw request body, mapping storage failures to readable errors."""

    try:
        return await store.write_temp_stream(chunks, max_bytes=max_bytes)
    except StorageError as error:
        code = str(error)
        if code == "STORAGE_TOO_LARGE":
            raise ResourceError(code, "文件超过大小上限", 413) from error
        if code == "STORAGE_EMPTY_UPLOAD":
            raise ResourceError(code, "上传内容为空", 400) from error
        raise ResourceError(code, "上传失败", 400) from error


async def store_variant(
    db: AsyncSession,
    *,
    actor: User,
    resource: Resource,
    variant: str,
    staged: Path,
    size_bytes: int,
    sha256: str,
    filename: str | None,
    declared_mime: str | None,
    settings: Settings,
) -> ResourceUploadReceipt:
    """Validate + store one already-staged file; replace any existing variant."""

    if actor.role != "admin":
        raise ResourceError("RESOURCE_FORBIDDEN", "仅管理员可上传资源文件", 403)
    if variant not in {"SOURCE", "PREVIEW"}:
        raise ResourceError("RESOURCE_VARIANT_INVALID", "资源变体无效", 422)

    store = store_for(settings)
    try:
        validated = validate_upload(
            staged=staged,
            filename=filename,
            declared_mime=declared_mime,
            kind=resource.kind,
            size_bytes=size_bytes,
            sha256=sha256,
            max_bytes=settings.resource_upload_max_bytes,
        )
    except UploadRejected as rejected:
        store.cleanup_temp(staged)
        raise ResourceError(rejected.code, rejected.message, rejected.status_code) from rejected

    key = build_storage_key(resource_id=resource.id, variant=variant, extension=validated.extension)
    store.publish_temp(staged, key)

    existing = await db.scalar(
        select(ResourceVariant).where(
            ResourceVariant.resource_id == resource.id,
            ResourceVariant.variant == variant,
        )
    )
    old_key = existing.storage_key if existing is not None else None
    if existing is None:
        db.add(
            ResourceVariant(
                resource_id=resource.id,
                variant=variant,
                storage_key=key,
                original_filename=validated.original_filename,
                declared_mime=(declared_mime or "").split(";")[0].strip().lower(),
                detected_mime=validated.mime,
                size_bytes=validated.size_bytes,
                sha256=validated.sha256,
            )
        )
    else:
        existing.storage_key = key
        existing.original_filename = validated.original_filename
        existing.declared_mime = (declared_mime or "").split(";")[0].strip().lower()
        existing.detected_mime = validated.mime
        existing.size_bytes = validated.size_bytes
        existing.sha256 = validated.sha256
    await db.commit()
    if old_key is not None and old_key != key:
        try:
            store.remove(old_key)
        except StorageError:  # pragma: no cover - best effort cleanup
            pass

    return ResourceUploadReceipt(
        resource_id=resource.id,
        variant=variant,  # type: ignore[arg-type]
        filename=validated.original_filename,
        mime=validated.mime,
        size_bytes=validated.size_bytes,
        sha256=validated.sha256,
    )


# --------------------------------------------------------------------------- #
# delivery
# --------------------------------------------------------------------------- #
def content_disposition(variant: ResourceVariant, *, inline: bool) -> str:
    """Word/PPT are always downloads: no in-browser active rendering."""

    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", variant.original_filename) or "resource"
    inline_ok = variant.detected_mime.startswith("video/") or variant.detected_mime.startswith(
        "image/"
    )
    if inline and inline_ok:
        return f'inline; filename="{ascii_name}"'
    return f'attachment; filename="{ascii_name}"'


async def resolve_variant(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    resource_id: uuid.UUID,
    variant: str,
    settings: Settings,
) -> tuple[Resource, ResourceVariant, Path]:
    if variant not in {"SOURCE", "PREVIEW"}:
        raise ResourceError("RESOURCE_VARIANT_INVALID", "资源变体无效", 422)
    resource = await load_visible_resource(db, viewer=viewer, resource_id=resource_id)
    row = await db.scalar(
        select(ResourceVariant).where(
            ResourceVariant.resource_id == resource.id,
            ResourceVariant.variant == variant,
        )
    )
    if row is None:
        raise ResourceFileMissing("资源文件未登记")
    store = store_for(settings)
    try:
        path = store.resolve(row.storage_key)
    except StorageError as error:
        raise ResourceFileMissing() from error
    if not path.is_file():
        raise ResourceFileMissing()
    return resource, row, path


async def issue_ticket(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    owner_user_id: uuid.UUID,
    resource_id: uuid.UUID,
    variant: str,
    settings: Settings,
) -> ResourceTicketDTO:
    await resolve_variant(
        db, viewer=viewer, resource_id=resource_id, variant=variant, settings=settings
    )
    token, expires = sign_ticket(
        settings.app_session_secret or "",
        resource_id=resource_id,
        variant=variant,
        owner_user_id=owner_user_id,
        ttl_seconds=settings.resource_ticket_ttl_seconds,
    )
    return ResourceTicketDTO(
        url=f"/api/v1/resources/content/{token}",
        expires_at=datetime.fromtimestamp(expires, tz=UTC),
        variant=variant,  # type: ignore[arg-type]
        notice=TICKET_NOTICE,
    )


async def consume_ticket(
    db: AsyncSession,
    *,
    viewer: ViewerScope,
    owner_user_id: uuid.UUID,
    token: str,
    settings: Settings,
) -> tuple[Resource, ResourceVariant, Path]:
    """Verify a signed ticket and re-check visibility at use time."""

    try:
        payload = verify_ticket(settings.app_session_secret or "", token)
    except Exception as error:  # TicketError carries the readable code
        code = getattr(error, "code", "RESOURCE_TICKET_INVALID")
        message = getattr(error, "message", "资源链接无效")
        raise ResourceError(code, message, 403) from error
    if payload["o"] != str(owner_user_id):
        # A leaked link is not enough: it must be used by the same account.
        raise ResourceError("RESOURCE_TICKET_OWNER", "资源链接不属于当前账号", 403)
    return await resolve_variant(
        db,
        viewer=viewer,
        resource_id=uuid.UUID(payload["r"]),
        variant=payload["v"],
        settings=settings,
    )


def security_headers(variant: ResourceVariant, *, inline: bool) -> dict[str, str]:
    """No same-origin execution of untrusted content, no caching of old links."""

    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Content-Disposition": content_disposition(variant, inline=inline),
        "Cross-Origin-Resource-Policy": "same-origin",
    }
    return headers


async def resource_summary(
    db: AsyncSession, resource: Resource, *, settings: Settings | None = None
) -> ResourceSummaryDTO:
    return await _summary(db, resource, settings=settings)


__all__ = [
    "ResourceError",
    "ResourceFileMissing",
    "ResourceNotVisible",
    "ResourceStateError",
    "allowed_resource_ids_for_teaching",
    "authorized_resource_ids_for_teaching",
    "consume_ticket",
    "create_resource",
    "issue_ticket",
    "list_student_resources",
    "load_visible_resource",
    "patch_resource",
    "resolve_variant",
    "resource_detail",
    "resource_summary",
    "security_headers",
    "select_resource_candidates",
    "store_for",
    "stage_upload",
    "store_variant",
    "visibility_condition",
]
