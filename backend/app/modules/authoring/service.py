"""Authoring service: job lifecycle, human review and publication (T22).

Separation of powers enforced here *and* in the database:

* The Designer produces a structured spec only. It never writes a review and
  never sets ``HUMAN_APPROVED`` — :func:`approve_package` requires an
  authenticated admin user, and the DB trigger re-checks that a real review row
  plus a verified artefact exist.
* ``asset_request`` is recorded for transparency and never becomes an artefact.
* Publication is idempotent through ``idempotency_key`` and requires a verified
  artefact; the exported bundle index is append-only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.authoring.bundle import publish_to_bundle
from app.modules.authoring.errors import AuthoringError
from app.modules.authoring.material import load_authoring_material
from app.modules.authoring.models import (
    AuthoringArtifact,
    AuthoringJob,
    AuthoringPackage,
    AuthoringPublication,
    AuthoringReview,
)
from app.modules.authoring.renderer import RenderError, render_package, verify_artifact
from app.modules.identity.models import User, UserRole


def _fail(code: str, message: str, status_code: int = 400) -> None:
    raise AuthoringError(code, message, status_code)


def is_human_admin(user: User | None) -> bool:
    """The only actor kind allowed to approve."""

    return user is not None and user.role == UserRole.ADMIN.value


# --------------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------------- #
async def create_job(
    db: AsyncSession,
    *,
    settings: Settings,
    actor: User,
    chapter_revision_id: uuid.UUID,
    idempotency_key: str,
    max_attempts: int | None = None,
) -> AuthoringJob:
    existing = await db.scalar(
        select(AuthoringJob).where(AuthoringJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    # Fail closed *before* a job row exists: the bound revision must exist, be
    # readable (not withdrawn) and carry real source text.
    await load_authoring_material(db, revision_id=chapter_revision_id)
    budget = max_attempts or settings.authoring_max_attempts
    job = AuthoringJob(
        owner_user_id=actor.id,
        chapter_revision_id=chapter_revision_id,
        operation="LESSON_PACKAGE_DRAFT",
        status="QUEUED",
        attempt=0,
        max_attempts=max(1, min(budget, settings.authoring_max_attempts)),
        gateway_mode=settings.gateway_mode,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def cancel_job(db: AsyncSession, *, job: AuthoringJob) -> AuthoringJob:
    if job.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        return job  # idempotent
    job.status = "CANCELLED"
    job.error_code = "AUTHORING_CANCELLED"
    await db.commit()
    await db.refresh(job)
    return job


async def retry_job(db: AsyncSession, *, job: AuthoringJob) -> AuthoringJob:
    if job.status in {"QUEUED", "RUNNING"}:
        _fail("AUTHORING_JOB_ACTIVE", "任务正在执行，不能重试", 409)
    if job.attempt >= job.max_attempts:
        job.status = "FAILED"
        job.error_code = "AUTHORING_RETRY_BUDGET_EXHAUSTED"
        await db.commit()
        _fail("AUTHORING_RETRY_BUDGET_EXHAUSTED", "重试次数已达上限", 409)
    job.status = "QUEUED"
    job.error_code = None
    job.run_ref = None
    await db.commit()
    await db.refresh(job)
    return job


async def claim_attempt(db: AsyncSession, *, job_id: uuid.UUID) -> AuthoringJob | None:
    """Short transaction: move QUEUED -> RUNNING and spend one attempt."""

    job = await db.scalar(select(AuthoringJob).where(AuthoringJob.id == job_id))
    if job is None or job.status != "QUEUED":
        return None
    if job.attempt >= job.max_attempts:
        job.status = "FAILED"
        job.error_code = "AUTHORING_RETRY_BUDGET_EXHAUSTED"
        await db.commit()
        return None
    job.attempt += 1
    job.status = "RUNNING"
    job.run_ref = f"designer-{job.id}-{job.attempt}"
    await db.commit()
    await db.refresh(job)
    return job


async def complete_job_failure(db: AsyncSession, *, job_id: uuid.UUID, code: str) -> None:
    job = await db.scalar(select(AuthoringJob).where(AuthoringJob.id == job_id))
    if job is None or job.status == "CANCELLED":
        return
    job.status = "FAILED"
    job.error_code = code[:64]
    await db.commit()


async def store_package(
    db: AsyncSession, *, settings: Settings, job: AuthoringJob, spec: dict
) -> AuthoringPackage:
    """Persist the validated Designer spec and render the real files."""

    if job.status == "CANCELLED":
        _fail("AUTHORING_JOB_CANCELLED", "任务已取消", 409)
    asset_requests = spec.get("asset_requests") or []
    if not isinstance(asset_requests, list):  # pragma: no cover - schema enforced
        _fail("AUTHORING_ASSET_REQUESTS_INVALID", "asset_requests 必须是数组")

    package = AuthoringPackage(
        job_id=job.id,
        chapter_revision_id=job.chapter_revision_id,
        title=str(spec.get("title") or "（未命名课时）")[:200],
        spec=spec,
        asset_requests=asset_requests,
        status="AUTO_VALIDATED",
        revision=1,
    )
    db.add(package)
    await db.flush()
    try:
        rendered = render_package(
            settings,
            package_id=str(package.id),
            chapter_revision_id=str(job.chapter_revision_id),
            spec=spec,
        )
    except RenderError as error:
        await db.rollback()
        _fail(error.code, error.message, 422)
    for item in rendered:
        db.add(
            AuthoringArtifact(
                package_id=package.id,
                kind=item.kind,
                storage_key=item.storage_key,
                original_filename=item.filename,
                detected_mime=item.mime,
                size_bytes=item.size_bytes,
                sha256=item.sha256,
                rendered_by="LOCAL_DETERMINISTIC_V1",
                verified_at=None,
            )
        )
    await db.flush()
    # A job only completes when the freshly rendered bytes really exist on disk
    # and match their recorded digests (V2: no real file ⇒ no completion).
    verified = await verify_package_artifacts(db, settings=settings, package=package)
    if not verified or any(row.verified_at is None for row in verified):
        await db.rollback()
        _fail("AUTHORING_NO_VERIFIED_ARTIFACT", "渲染后的文件校验失败，任务未完成", 422)
    job.status = "SUCCEEDED"
    job.error_code = None
    await db.commit()
    await db.refresh(package)
    return package


async def verify_package_artifacts(
    db: AsyncSession, *, settings: Settings, package: AuthoringPackage
) -> list[AuthoringArtifact]:
    """Re-read every artefact from disk; only verified rows keep ``verified_at``."""

    rows = list(
        await db.scalars(
            select(AuthoringArtifact).where(AuthoringArtifact.package_id == package.id)
        )
    )
    for row in rows:
        ok = verify_artifact(
            settings,
            storage_key=row.storage_key,
            sha256=row.sha256,
            size_bytes=row.size_bytes,
        )
        row.verified_at = datetime.now(UTC) if ok else None
    await db.commit()
    return rows


# --------------------------------------------------------------------------- #
# human review
# --------------------------------------------------------------------------- #
async def approve_package(
    db: AsyncSession,
    *,
    settings: Settings,
    package: AuthoringPackage,
    actor: User | None,
    comment: str = "",
) -> AuthoringReview:
    """Only a real admin session may approve; automation is refused here."""

    if not is_human_admin(actor):
        _fail("AUTHORING_HUMAN_ONLY", "只有真实管理员的人工审校操作可以批准", 403)
    assert actor is not None  # narrowed by is_human_admin

    artifacts = await verify_package_artifacts(db, settings=settings, package=package)
    # Every rendered file must re-verify: a package with one missing/edited
    # artifact is not approvable (V2), not "mostly fine".
    if not artifacts or any(row.verified_at is None for row in artifacts):
        _fail(
            "AUTHORING_NO_VERIFIED_ARTIFACT",
            "有文件缺失或校验失败，不能进入人工通过",
            409,
        )
    review = AuthoringReview(
        package_id=package.id,
        actor_user_id=actor.id,
        actor_kind="HUMAN_ADMIN",
        decision="APPROVED",
        comment=comment[:2000],
        package_revision=package.revision,
    )
    db.add(review)
    await db.flush()
    package.status = "HUMAN_APPROVED"
    await db.commit()
    await db.refresh(review)
    return review


async def reject_package(
    db: AsyncSession, *, package: AuthoringPackage, actor: User | None, comment: str = ""
) -> AuthoringReview:
    if not is_human_admin(actor):
        _fail("AUTHORING_HUMAN_ONLY", "只有真实管理员的人工审校操作可以驳回", 403)
    assert actor is not None
    review = AuthoringReview(
        package_id=package.id,
        actor_user_id=actor.id,
        actor_kind="HUMAN_ADMIN",
        decision="REJECTED",
        comment=comment[:2000],
        package_revision=package.revision,
    )
    db.add(review)
    await db.flush()
    package.status = "DRAFT"
    await db.commit()
    await db.refresh(review)
    return review


# --------------------------------------------------------------------------- #
# publication
# --------------------------------------------------------------------------- #
async def publish_package(
    db: AsyncSession,
    *,
    settings: Settings,
    package: AuthoringPackage,
    actor: User | None,
    idempotency_key: str,
) -> tuple[AuthoringPublication, bool]:
    """Idempotent publish. Returns ``(publication, created)``."""

    if not is_human_admin(actor):
        _fail("AUTHORING_HUMAN_ONLY", "只有真实管理员可以发布", 403)
    assert actor is not None

    existing = await db.scalar(
        select(AuthoringPublication).where(AuthoringPublication.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing, False  # same intent: never a second formal revision

    if package.status not in {"HUMAN_APPROVED", "PUBLISHED"}:
        _fail("AUTHORING_NOT_APPROVED", "只有人工通过的教学包可以发布", 409)

    rows = await verify_package_artifacts(db, settings=settings, package=package)
    verified = [row for row in rows if row.verified_at is not None]
    if not verified or any(row.verified_at is None for row in rows):
        _fail("AUTHORING_NO_VERIFIED_ARTIFACT", "有文件缺失或校验失败，不能发布", 409)

    next_revision = (
        await db.scalar(
            select(func.coalesce(func.max(AuthoringPublication.revision), 0)).where(
                AuthoringPublication.package_id == package.id
            )
        )
    ) + 1
    manifest = next((row for row in verified if row.kind == "PACKAGE_MANIFEST"), None)
    digest = manifest.sha256 if manifest is not None else sorted(row.sha256 for row in verified)[0]
    publication = AuthoringPublication(
        package_id=package.id,
        revision=next_revision,
        published_by_user_id=actor.id,
        chapter_revision_id=package.chapter_revision_id,
        artifact_sha256=digest,
        bundle_ref="",
        idempotency_key=idempotency_key,
    )
    db.add(publication)
    await db.flush()
    bundle_ref = publish_to_bundle(
        settings,
        package_id=str(package.id),
        package_revision=next_revision,
        chapter_revision_id=str(package.chapter_revision_id),
        artifact_sha256=digest,
        title=package.title,
        published_by=str(actor.id),
    )
    publication.bundle_ref = bundle_ref
    package.status = "PUBLISHED"
    package.published_revision = next_revision
    await db.commit()
    await db.refresh(publication)
    return publication, True


__all__ = [
    "AuthoringError",
    "approve_package",
    "cancel_job",
    "claim_attempt",
    "complete_job_failure",
    "create_job",
    "is_human_admin",
    "publish_package",
    "reject_package",
    "retry_job",
    "store_package",
    "verify_package_artifacts",
]
