"""Admin authoring API (T22): jobs, packages, human review, publication.

Every route requires a real admin session (T05). The review route is the only
way to reach HUMAN_APPROVED and it is additionally re-checked by a database
trigger, so no AI/automation path can self-approve.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.database import get_session
from app.jobs.authoring_worker import execute_job
from app.modules.authoring.models import (
    AuthoringArtifact,
    AuthoringJob,
    AuthoringPackage,
    AuthoringPublication,
    AuthoringReview,
)
from app.modules.authoring.service import (
    AuthoringError,
    approve_package,
    cancel_job,
    create_job,
    publish_package,
    reject_package,
    retry_job,
)
from app.modules.content.models import Chapter, ChapterReviewState, ChapterRevision, Course
from app.modules.identity.dependencies import SessionContext, csrf_dependency, require_admin

router = APIRouter(tags=["authoring-admin"])

BACKGROUND_TASKS: set[asyncio.Task] = set()


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_revision_id: uuid.UUID
    idempotency_key: str = Field(min_length=3, max_length=120)
    max_attempts: int | None = Field(default=None, ge=1, le=5)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(default="", max_length=2000)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=3, max_length=120)


class AdminChapterRevisionDTO(BaseModel):
    id: uuid.UUID
    revision: int
    chapter_id: uuid.UUID
    chapter_title: str
    course_id: uuid.UUID
    course_title: str
    stage: str
    review_status: str
    publication_status: str
    created_at: datetime
    updated_at: datetime | None


class AdminChapterRevisionListDTO(BaseModel):
    items: list[AdminChapterRevisionDTO]
    total: int
    limit: int
    offset: int


class AdminAuthoringJobDTO(BaseModel):
    id: uuid.UUID
    chapter_revision_id: uuid.UUID
    revision: int
    chapter_id: uuid.UUID
    chapter_title: str
    course_id: uuid.UUID
    course_title: str
    operation: str
    status: str
    attempt: int
    max_attempts: int
    run_ref: str | None
    error_code: str | None
    gateway_mode: str
    package_id: uuid.UUID | None
    package_title: str | None
    package_status: str | None
    created_at: datetime
    updated_at: datetime


class AdminAuthoringJobListDTO(BaseModel):
    items: list[AdminAuthoringJobDTO]
    total: int
    limit: int
    offset: int


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _raise(error: AuthoringError) -> None:
    raise HTTPException(status_code=error.status_code, detail=f"{error.code}: {error.message}")


def _schedule(settings: Settings, job_id: uuid.UUID) -> None:
    task = asyncio.create_task(execute_job(settings, job_id))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)


async def _job_or_404(db: AsyncSession, job_id: uuid.UUID) -> AuthoringJob:
    job = await db.scalar(select(AuthoringJob).where(AuthoringJob.id == job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="AUTHORING_JOB_NOT_FOUND: 任务不存在")
    return job


async def _package_or_404(db: AsyncSession, package_id: uuid.UUID) -> AuthoringPackage:
    package = await db.scalar(select(AuthoringPackage).where(AuthoringPackage.id == package_id))
    if package is None:
        raise HTTPException(status_code=404, detail="AUTHORING_PACKAGE_NOT_FOUND: 教学包不存在")
    return package


def _job_dto(job: AuthoringJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "chapter_revision_id": str(job.chapter_revision_id),
        "operation": job.operation,
        "status": job.status,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "run_ref": job.run_ref,
        "error_code": job.error_code,
        "gateway_mode": job.gateway_mode,
        "idempotency_key": job.idempotency_key,
    }


async def _package_dto(db: AsyncSession, package: AuthoringPackage) -> dict[str, Any]:
    artifacts = list(
        await db.scalars(
            select(AuthoringArtifact).where(AuthoringArtifact.package_id == package.id)
        )
    )
    reviews = list(
        await db.scalars(select(AuthoringReview).where(AuthoringReview.package_id == package.id))
    )
    publications = list(
        await db.scalars(
            select(AuthoringPublication).where(AuthoringPublication.package_id == package.id)
        )
    )
    return {
        "id": str(package.id),
        "job_id": str(package.job_id),
        "chapter_revision_id": str(package.chapter_revision_id),
        "title": package.title,
        "status": package.status,
        "revision": package.revision,
        "published_revision": package.published_revision,
        "spec": package.spec,
        "asset_requests": package.asset_requests,
        "artifacts": [
            {
                "kind": item.kind,
                "filename": item.original_filename,
                "mime": item.detected_mime,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "rendered_by": item.rendered_by,
                "verified": item.verified_at is not None,
            }
            for item in artifacts
        ],
        "reviews": [
            {
                "actor_user_id": str(item.actor_user_id),
                "actor_kind": item.actor_kind,
                "decision": item.decision,
                "comment": item.comment,
                "package_revision": item.package_revision,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in reviews
        ],
        "publications": [
            {
                "revision": item.revision,
                "bundle_ref": item.bundle_ref,
                "idempotency_key": item.idempotency_key,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in publications
        ],
        "notice": (
            "asset_requests 是待人工提供的素材请求，不是产物；只有真实文件才会计入 artifacts。"
        ),
    }


@router.get("/admin/content/revisions", response_model=AdminChapterRevisionListDTO)
async def list_admin_chapter_revisions(
    q: str | None = Query(default=None, max_length=100),
    course_id: uuid.UUID | None = None,
    chapter_id: uuid.UUID | None = None,
    stage: Literal["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"] | None = None,
    publication_status: Literal["DRAFT", "PUBLISHED", "WITHDRAWN"] | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> AdminChapterRevisionListDTO:
    """Admin-only curriculum selector, including unpublished revisions."""
    conditions = []
    if course_id:
        conditions.append(Course.id == course_id)
    if chapter_id:
        conditions.append(Chapter.id == chapter_id)
    if stage:
        conditions.append(ChapterRevision.stage == stage)
    if publication_status:
        conditions.append(
            func.coalesce(ChapterReviewState.publication_status, "DRAFT") == publication_status
        )
    if q:
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if escaped:
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    Course.title.ilike(pattern, escape="\\"),
                    Chapter.title.ilike(pattern, escape="\\"),
                )
            )
    base = (
        select(ChapterRevision, Chapter, Course, ChapterReviewState)
        .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
        .join(Course, Course.id == Chapter.course_id)
        .outerjoin(ChapterReviewState, ChapterReviewState.revision_id == ChapterRevision.id)
        .where(*conditions)
    )
    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (
        await db.execute(
            base.order_by(Course.title, Chapter.order_index, ChapterRevision.revision.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return AdminChapterRevisionListDTO(
        items=[
            AdminChapterRevisionDTO(
                id=revision.id,
                revision=revision.revision,
                chapter_id=chapter.id,
                chapter_title=chapter.title,
                course_id=course.id,
                course_title=course.title,
                stage=revision.stage,
                review_status=review.review_status if review else "UNREVIEWED",
                publication_status=review.publication_status if review else "DRAFT",
                created_at=revision.created_at,
                updated_at=review.updated_at if review else None,
            )
            for revision, chapter, course, review in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/authoring/jobs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_dependency)],
)
async def create_authoring_job(
    payload: JobCreateRequest,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = _settings(request)
    try:
        job = await create_job(
            db,
            settings=settings,
            actor=context.user,
            chapter_revision_id=payload.chapter_revision_id,
            idempotency_key=payload.idempotency_key,
            max_attempts=payload.max_attempts,
        )
    except AuthoringError as error:
        # fail closed before any job row exists (missing/withdrawn/no material)
        _raise(error)
    if job.status == "QUEUED" and settings.authoring_autorun:
        _schedule(settings, job.id)
    return _job_dto(job)


@router.get("/admin/authoring/jobs", response_model=AdminAuthoringJobListDTO)
async def list_authoring_jobs(
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> AdminAuthoringJobListDTO:
    conditions = [AuthoringJob.status == status] if status else []
    total = int(
        await db.scalar(select(func.count()).select_from(AuthoringJob).where(*conditions)) or 0
    )
    rows = (
        await db.execute(
            select(AuthoringJob, ChapterRevision, Chapter, Course)
            .join(ChapterRevision, ChapterRevision.id == AuthoringJob.chapter_revision_id)
            .join(Chapter, Chapter.id == ChapterRevision.chapter_id)
            .join(Course, Course.id == Chapter.course_id)
            .where(*conditions)
            .order_by(AuthoringJob.created_at.desc(), AuthoringJob.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    packages: dict[uuid.UUID, AuthoringPackage] = {}
    if rows:
        package_rows = await db.scalars(
            select(AuthoringPackage)
            .where(AuthoringPackage.job_id.in_([job.id for job, _, _, _ in rows]))
            .order_by(AuthoringPackage.created_at.desc(), AuthoringPackage.id.desc())
        )
        for package in package_rows:
            packages.setdefault(package.job_id, package)
    return AdminAuthoringJobListDTO(
        items=[
            AdminAuthoringJobDTO(
                id=job.id,
                chapter_revision_id=revision.id,
                revision=revision.revision,
                chapter_id=chapter.id,
                chapter_title=chapter.title,
                course_id=course.id,
                course_title=course.title,
                operation=job.operation,
                status=job.status,
                attempt=job.attempt,
                max_attempts=job.max_attempts,
                run_ref=job.run_ref,
                error_code=job.error_code,
                gateway_mode=job.gateway_mode,
                package_id=packages[job.id].id if job.id in packages else None,
                package_title=packages[job.id].title if job.id in packages else None,
                package_status=packages[job.id].status if job.id in packages else None,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            for job, revision, chapter, course in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/admin/authoring/jobs/{job_id}")
async def read_authoring_job(
    job_id: uuid.UUID,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = await _job_or_404(db, job_id)
    package = await db.scalar(select(AuthoringPackage).where(AuthoringPackage.job_id == job.id))
    body = _job_dto(job)
    body["package_id"] = str(package.id) if package is not None else None
    return body


@router.post("/admin/authoring/jobs/{job_id}/cancel", dependencies=[Depends(csrf_dependency)])
async def cancel_authoring_job(
    job_id: uuid.UUID,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = await _job_or_404(db, job_id)
    return _job_dto(await cancel_job(db, job=job))


@router.post("/admin/authoring/jobs/{job_id}/retry", dependencies=[Depends(csrf_dependency)])
async def retry_authoring_job(
    job_id: uuid.UUID,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = await _job_or_404(db, job_id)
    try:
        job = await retry_job(db, job=job)
    except AuthoringError as error:
        _raise(error)
    settings = _settings(request)
    if settings.authoring_autorun:
        _schedule(settings, job.id)
    return _job_dto(job)


@router.get("/admin/authoring/packages/{package_id}")
async def read_authoring_package(
    package_id: uuid.UUID,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await _package_dto(db, await _package_or_404(db, package_id))


@router.post(
    "/admin/authoring/packages/{package_id}/approve",
    dependencies=[Depends(csrf_dependency)],
)
async def approve_authoring_package(
    package_id: uuid.UUID,
    payload: ReviewRequest,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    package = await _package_or_404(db, package_id)
    try:
        await approve_package(
            db,
            settings=_settings(request),
            package=package,
            actor=context.user,
            comment=payload.comment,
        )
    except AuthoringError as error:
        _raise(error)
    return await _package_dto(db, package)


@router.post(
    "/admin/authoring/packages/{package_id}/reject",
    dependencies=[Depends(csrf_dependency)],
)
async def reject_authoring_package(
    package_id: uuid.UUID,
    payload: ReviewRequest,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    package = await _package_or_404(db, package_id)
    try:
        await reject_package(db, package=package, actor=context.user, comment=payload.comment)
    except AuthoringError as error:
        _raise(error)
    return await _package_dto(db, package)


@router.post(
    "/admin/authoring/packages/{package_id}/publish",
    dependencies=[Depends(csrf_dependency)],
)
async def publish_authoring_package(
    package_id: uuid.UUID,
    payload: PublishRequest,
    request: Request,
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    package = await _package_or_404(db, package_id)
    try:
        publication, created = await publish_package(
            db,
            settings=_settings(request),
            package=package,
            actor=context.user,
            idempotency_key=payload.idempotency_key,
        )
    except AuthoringError as error:
        _raise(error)
    return {
        "publication": {
            "revision": publication.revision,
            "bundle_ref": publication.bundle_ref,
            "idempotency_key": publication.idempotency_key,
        },
        "created": created,
        "package": await _package_dto(db, package),
    }


__all__ = ["router"]
