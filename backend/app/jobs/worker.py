"""Durable polling consumer for queued teaching and authoring work.

The API may keep its in-process fast path in development. A deployment sets
``TEACHING_AUTORUN=false`` and ``AUTHORING_AUTORUN=false`` so this process is
the single consumer. Teaching leases make a restart or duplicate poll safe;
authoring claims are consumed serially by this worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import uuid
from collections.abc import Awaitable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.integrations.knodo.gateway import build_gateway
from app.jobs.authoring_worker import execute_job, recover_authoring_jobs
from app.jobs.teaching_worker import execute_run, recover_runs
from app.modules.authoring.models import AuthoringJob
from app.modules.teaching.models import AgentRun

logger = logging.getLogger("k12.worker")


def _poll_seconds() -> float:
    raw = os.environ.get("WORKER_POLL_SECONDS", "1")
    try:
        return max(0.2, min(float(raw), 30.0))
    except ValueError:
        return 1.0


async def _queued_ids(settings: Settings) -> tuple[list[str], list[str]]:
    engine = get_engine(settings.active_database_url, settings.app_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        teaching = [
            str(value)
            for value in (
                await db.scalars(select(AgentRun.id).where(AgentRun.status == "QUEUED").limit(8))
            ).all()
        ]
        authoring = [
            str(value)
            for value in (
                await db.scalars(
                    select(AuthoringJob.id).where(AuthoringJob.status == "QUEUED").limit(4)
                )
            ).all()
        ]
    return teaching, authoring


async def run_once(settings: Settings | None = None) -> dict[str, int]:
    runtime = settings or Settings()
    recovered_teaching = await recover_runs(runtime)
    recovered_authoring = await recover_authoring_jobs(runtime)
    teaching_ids, authoring_ids = await _queued_ids(runtime)
    gateway = build_gateway(runtime)
    try:
        for run_id in teaching_ids:
            await execute_run(runtime, gateway, run_id)
        for job_id in authoring_ids:
            await execute_job(runtime, uuid.UUID(job_id))
    finally:
        await gateway.aclose()
    return {
        "recovered_teaching": recovered_teaching,
        "recovered_authoring": recovered_authoring,
        "teaching_processed": len(teaching_ids),
        "authoring_processed": len(authoring_ids),
    }


async def serve(stop: Awaitable[object] | None = None) -> None:
    settings = Settings()
    stop_event = asyncio.Event()
    if stop is not None:
        asyncio.create_task(stop).add_done_callback(lambda _: stop_event.set())
    while not stop_event.is_set():
        try:
            outcome = await run_once(settings)
            if any(outcome[key] for key in ("recovered_teaching", "recovered_authoring")):
                logger.warning("worker recovery: %s", outcome)
        except Exception:  # pragma: no cover - process boundary
            logger.exception("worker poll failed; retrying")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_poll_seconds())
        except TimeoutError:
            continue


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop = asyncio.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    if os.environ.get("WORKER_ONESHOT") == "1":
        print(json.dumps(loop.run_until_complete(run_once()), sort_keys=True))
    else:
        loop.run_until_complete(serve(stop.wait()))


if __name__ == "__main__":
    main()
