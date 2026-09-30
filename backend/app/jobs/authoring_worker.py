"""Designer LESSON_PACKAGE_DRAFT worker (T22 V1/V2/V5).

Transaction discipline (same shape as the teaching worker):

1. short transaction: QUEUED -> RUNNING, spend one attempt from the budget;
2. **no transaction**: call the Designer through the frozen gateway abstraction;
3. short transaction: validate the returned structured spec and store the
   package, then render the real files.

The gateway is never called for ``gateway_mode='knodo'`` unless a live
authorisation exists: without it the job fails closed with
``AUTHORING_LIVE_NOT_AUTHORIZED`` and the report stays honest.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.integrations.knodo.gateway import AgentGateway, build_gateway
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.integrations.knodo.types import GatewayStatus
from app.modules.ai.service import target_arguments
from app.modules.authoring.errors import AuthoringError
from app.modules.authoring.material import build_package_request, load_authoring_material
from app.modules.authoring.models import AuthoringJob
from app.modules.authoring.service import (
    claim_attempt,
    complete_job_failure,
    store_package,
)

logger = logging.getLogger(__name__)

LIVE_NOT_AUTHORIZED = "AUTHORING_LIVE_NOT_AUTHORIZED"
GATEWAY_DISABLED = "AUTHORING_GATEWAY_DISABLED"
STALE_RUNNING = "AUTHORING_WORKER_RESTARTED"
SPEC_INVALID = "AUTHORING_SPEC_INVALID"


def session_factory(settings: Settings) -> async_sessionmaker:
    return async_sessionmaker(engine_for(settings), expire_on_commit=False)


def engine_for(settings: Settings):
    return get_engine(settings.active_database_url, settings.app_env)


def validate_spec(payload: object) -> tuple[dict | None, str | None]:
    """Validate against the frozen lesson-package-draft schema."""

    registry = default_registry()
    errors = registry.validate_response(Operation.LESSON_PACKAGE_DRAFT, payload)
    if errors:
        return None, SPEC_INVALID
    assert isinstance(payload, dict)
    return payload, None


async def execute_job(settings: Settings, job_id: uuid.UUID) -> str:
    """Run one job attempt. Returns the terminal status it reached."""

    factory = session_factory(settings)
    async with factory() as db:
        job = await claim_attempt(db, job_id=job_id)
        if job is None:
            return "NO_ATTEMPT"
        gateway_mode = job.gateway_mode
        run_ref = job.run_ref
        try:
            # Server-side truth only: the exact revision the job is bound to.
            material = await load_authoring_material(db, revision_id=job.chapter_revision_id)
        except AuthoringError as error:
            await complete_job_failure(db, job_id=job_id, code=error.code)
            return "FAILED"
        request = build_package_request(material, request_id=run_ref or f"designer-{job.id}")

        target_options = await target_arguments(
            db, Operation.LESSON_PACKAGE_DRAFT, request, require_route=gateway_mode == "knodo"
        )

    if gateway_mode == "knodo":
        # no live authorisation is recorded for T22: fail closed, never call out
        async with factory() as db:
            await complete_job_failure(db, job_id=job_id, code=LIVE_NOT_AUTHORIZED)
        return "FAILED"
    if gateway_mode not in {"fixture", "disabled"}:
        async with factory() as db:
            await complete_job_failure(db, job_id=job_id, code=GATEWAY_DISABLED)
        return "FAILED"

    gateway: AgentGateway = build_gateway(settings)
    try:
        if gateway_mode == "fixture" and settings.authoring_fixture_delay_seconds > 0:
            await asyncio.sleep(settings.authoring_fixture_delay_seconds)
        result = await gateway.invoke(Operation.LESSON_PACKAGE_DRAFT, request, **target_options)
    except Exception as error:  # gateway failures are recorded, never guessed
        logger.warning("designer gateway failed for job %s: %s", run_ref, type(error).__name__)
        async with factory() as db:
            await complete_job_failure(db, job_id=job_id, code="AUTHORING_GATEWAY_FAILED")
        return "FAILED"

    if result.status is not GatewayStatus.OK or result.output is None:
        code = (
            result.error.reason_code
            if result.error is not None
            else f"AUTHORING_GATEWAY_{result.status.value}"
        )
        async with factory() as db:
            await complete_job_failure(db, job_id=job_id, code=code)
        return "FAILED"

    spec, error_code = validate_spec(result.output)
    if spec is None:
        async with factory() as db:
            await complete_job_failure(db, job_id=job_id, code=error_code or SPEC_INVALID)
        return "FAILED"

    async with factory() as db:
        job = await db.scalar(select(AuthoringJob).where(AuthoringJob.id == job_id))
        if job is None or job.status != "RUNNING":
            return "CANCELLED"
        try:
            await store_package(db, settings=settings, job=job, spec=spec)
        except AuthoringError as error:
            await db.rollback()
            await complete_job_failure(db, job_id=job_id, code=error.code)
            return "FAILED"
        except Exception as error:  # pragma: no cover - defensive
            logger.warning("authoring store failed for job %s: %s", job_id, type(error).__name__)
            await db.rollback()
            await complete_job_failure(db, job_id=job_id, code="AUTHORING_STORE_FAILED")
            return "FAILED"
    return "SUCCEEDED"


async def recover_authoring_jobs(settings: Settings) -> int:
    """Mark runs that were interrupted by a restart as failed (no zombie RUNNING)."""

    factory = session_factory(settings)
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.authoring_lease_seconds)
    recovered = 0
    async with factory() as db:
        rows = list(await db.scalars(select(AuthoringJob).where(AuthoringJob.status == "RUNNING")))
        for job in rows:
            if job.updated_at is not None and job.updated_at > cutoff:
                continue
            job.status = "FAILED"
            job.error_code = STALE_RUNNING
            recovered += 1
        await db.commit()
    return recovered


__all__ = [
    "GATEWAY_DISABLED",
    "LIVE_NOT_AUTHORIZED",
    "SPEC_INVALID",
    "execute_job",
    "recover_authoring_jobs",
    "session_factory",
    "validate_spec",
]
