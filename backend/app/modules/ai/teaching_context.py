"""Compose a server-owned target and bounded, account-scoped personal context."""

import json
from dataclasses import dataclass
from hashlib import sha256

from app.integrations.knodo.wire import KnodoTarget
from app.modules.ai.service import resolve
from app.modules.memory.automatic import KeywordMemoryRetriever, state_for, utcnow
from app.modules.memory.summaries import recall_summary


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
    summary = await recall_summary(db, session.owner_user_id, session.id, state, utcnow())
    if summary:
        items.append(summary)
    if scope and target_snapshot:
        scope += "|agent=" + target_snapshot["signature"]
        scope += f"|registry={target_snapshot['configuration_revision']}"
    if scope and state and state.content_revision:
        scope += f"|memory={state.content_revision}"
    if scope and (items or (state and state.content_revision)):
        # Expiry and changed recall also retire a continuation carrying old facts.
        digest = sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:24]
        scope += "|recall=" + digest
    return TeachingRuntimeContext(target, scope, items[:8])
