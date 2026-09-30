"""Independent durable memory consumer. Never runs in the teaching request path."""

import asyncio
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.modules.ai.extraction import ExtractionFailure, extract
from app.modules.ai.service import resolve
from app.modules.memory.automatic import SENSITIVE, apply_extraction, state_for, utcnow
from app.modules.memory.automatic_models import MemoryTask, PersonalMemoryItem, PersonalMemoryState
from app.modules.memory.contracts import ExtractionRequest, SourceMessage
from app.modules.teaching.models import ConversationMessage

logger = logging.getLogger("k12.memory_worker")


async def run_once(settings=None, *, extractor=extract):
    settings = settings or Settings()
    factory = async_sessionmaker(
        get_engine(settings.active_database_url, settings.app_env), expire_on_commit=False
    )
    now = utcnow()
    async with factory() as db:
        expired = list(
            await db.scalars(
                select(PersonalMemoryState)
                .where(PersonalMemoryState.lease_until < now)
                .with_for_update(skip_locked=True)
            )
        )
        for state in expired:
            await db.execute(
                update(MemoryTask)
                .where(
                    MemoryTask.owner_user_id == state.owner_user_id,
                    MemoryTask.status == "RUNNING",
                    MemoryTask.lease_token == state.lease_token,
                )
                .values(status="RETRY_REQUIRED", reason="INTERRUPTED_UNCERTAIN")
            )
            state.lease_token, state.lease_until = None, None
        await db.commit()
        owners = list(
            await db.scalars(
                select(MemoryTask.owner_user_id)
                .where(MemoryTask.status == "QUEUED", MemoryTask.available_at <= now)
                .distinct()
                .limit(20)
            )
        )
    for owner in owners:
        token = uuid.uuid4()
        async with factory() as db:
            state = await db.scalar(
                select(PersonalMemoryState)
                .where(PersonalMemoryState.owner_user_id == owner)
                .with_for_update(skip_locked=True)
            )
            if (
                state is None
                or not state.auto_enabled
                or (state.lease_until and state.lease_until > now)
            ):
                continue
            tasks = list(
                await db.scalars(
                    select(MemoryTask)
                    .where(
                        MemoryTask.owner_user_id == owner,
                        MemoryTask.status == "QUEUED",
                        MemoryTask.available_at <= now,
                    )
                    .order_by(MemoryTask.created_at)
                    .limit(20)
                )
            )
            if not tasks:
                continue
            first, last = tasks[0].created_at, tasks[-1].created_at
            is_backfill = any(t.reason == "BACKFILL" for t in tasks)
            if not is_backfill and now < min(
                last + timedelta(seconds=settings.memory_coalesce_seconds),
                first + timedelta(seconds=settings.memory_max_wait_seconds),
            ):
                continue
            state.lease_token, state.lease_until = (
                token,
                now + timedelta(seconds=settings.memory_extract_timeout_seconds + 30),
            )
            epoch = state.revision
            for task in tasks:
                task.status, task.lease_token = "RUNNING", token
                task.attempt += 1
            ids = [t.id for t in tasks]
            messages = list(
                await db.scalars(
                    select(ConversationMessage)
                    .where(
                        ConversationMessage.owner_user_id == owner,
                        ConversationMessage.run_id.in_([uuid.UUID(t.source_run_id) for t in tasks]),
                        ConversationMessage.role == "USER",
                    )
                    .order_by(ConversationMessage.created_at)
                )
            )
            sources = [
                SourceMessage(
                    id=str(m.id),
                    session_id=str(m.session_id),
                    observed_at=m.created_at.isoformat(),
                    text=m.content_markdown[:8000],
                )
                for m in messages
                if not SENSITIVE.search(m.content_markdown)
            ][:20]
            existing = list(
                await db.scalars(
                    select(PersonalMemoryItem)
                    .where(PersonalMemoryItem.owner_user_id == owner)
                    .order_by(PersonalMemoryItem.updated_at.desc())
                    .limit(200)
                )
            )
            payload = ExtractionRequest(
                request_id=str(token),
                sources=sources,
                existing=[
                    {
                        "key": m.key,
                        "statement": m.statement,
                        "status": m.status,
                        "manual": str(m.manual).lower(),
                    }
                    for m in existing
                ],
            )
            try:
                target = await resolve(db, "MEMORY_EXTRACT")
            except ValueError:
                target = None
            await db.commit()
        result, failure = None, None
        try:
            if sources:
                result = await extractor(settings, payload, target)
        except ExtractionFailure as exc:
            failure = exc
        except Exception:
            logger.exception("memory extraction failed (no message bodies logged)")
            failure = ExtractionFailure("MEMORY_PROCESSING_FAILED")
        async with factory() as db:
            state = await state_for(db, owner, lock=True, create=False)
            if state is None or state.lease_token != token:
                continue
            claimed = list(
                await db.scalars(
                    select(MemoryTask).where(
                        MemoryTask.id.in_(ids),
                        MemoryTask.status == "RUNNING",
                        MemoryTask.lease_token == token,
                    )
                )
            )
            valid = state.auto_enabled and state.revision == epoch and state.lease_until > utcnow()
            if valid and result:
                allowed_runs = {t.source_run_id for t in claimed}
                allowed_messages = {str(m.id) for m in messages if str(m.run_id) in allowed_runs}
                await apply_extraction(
                    db, owner, result, [s for s in sources if s.id in allowed_messages]
                )
            for task in claimed:
                task.status = "SUCCEEDED" if valid and failure is None else "CANCELLED"
                task.reason = None if task.status == "SUCCEEDED" else "MEMORY_CONTEXT_CHANGED"
                if valid and failure:
                    retry = failure.retryable and task.attempt < 3
                    task.status = "QUEUED" if retry else "RETRY_REQUIRED"
                    task.reason = failure.reason[:80]
                    task.available_at = utcnow() + timedelta(seconds=30 * task.attempt)
                task.updated_at = utcnow()
            state.lease_token, state.lease_until = None, None
            await db.commit()
        return len(ids)
    return 0


async def serve():
    settings = Settings()
    while True:
        try:
            await run_once(settings)
        except Exception:
            logger.exception("memory worker cycle failed")
        await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
