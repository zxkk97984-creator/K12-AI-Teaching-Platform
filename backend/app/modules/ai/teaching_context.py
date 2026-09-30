"""Compose a server-owned target and bounded, account-scoped personal context."""

from dataclasses import dataclass

from sqlalchemy import select

from app.integrations.knodo.wire import KnodoTarget
from app.modules.ai.service import resolve
from app.modules.memory.automatic import KeywordMemoryRetriever, state_for
from app.modules.memory.automatic_models import ConversationMemorySummary


@dataclass(frozen=True)
class TeachingRuntimeContext:
    target: KnodoTarget | None
    continuation_scope: str | None
    personal_items: list[dict[str, str]]


async def build_runtime_context(db, *, settings, gateway, session, operation, query: str):
    target_snapshot = await resolve(
        db,
        operation.value,
        session.stage,
        session.teacher_snapshot,
        require_route=settings.gateway_mode == "knodo",
    )
    target = (
        KnodoTarget(bot_id=target_snapshot["bot_id"], workspace_id=target_snapshot["workspace_id"])
        if target_snapshot
        else None
    )
    scope = gateway.continuation_scope(operation, **({"target": target} if target else {}))
    state = await state_for(db, session.owner_user_id, create=False)
    items = await KeywordMemoryRetriever().retrieve(db, session.owner_user_id, query)
    if state is None or state.use_enabled:
        summary = await db.scalar(
            select(ConversationMemorySummary).where(
                ConversationMemorySummary.owner_user_id == session.owner_user_id,
                ConversationMemorySummary.session_id == str(session.id),
            )
        )
        if summary and summary.content:
            items.append(
                {
                    "id": f"session-summary:{summary.id}:v{summary.revision}",
                    "source": "SESSION_SUMMARY",
                    "summary": summary.content,
                }
            )
    if scope and target_snapshot:
        scope += "|agent=" + target_snapshot["signature"]
        scope += f"|registry={target_snapshot['configuration_revision']}"
    if scope and state and state.content_revision:
        scope += f"|memory={state.content_revision}"
    return TeachingRuntimeContext(target, scope, items[:8])
