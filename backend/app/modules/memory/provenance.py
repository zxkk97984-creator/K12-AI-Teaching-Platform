"""Resolve extraction references against the account's real student messages."""

import uuid
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select

from app.modules.memory.contracts import SourceMessage
from app.modules.teaching.models import ConversationMessage, LessonSession


async def _messages_for(db, owner, source_ids):
    ids = set()
    for source_id in source_ids:
        try:
            ids.add(uuid.UUID(source_id))
        except (ValueError, TypeError, AttributeError):
            continue
    if not ids:
        return {}
    messages = await db.scalars(
        select(ConversationMessage)
        .join(LessonSession, LessonSession.id == ConversationMessage.session_id)
        .where(
            ConversationMessage.id.in_(ids),
            ConversationMessage.owner_user_id == owner,
            LessonSession.owner_user_id == owner,
            ConversationMessage.role == "USER",
        )
        .execution_options(populate_existing=True)
    )
    return {str(message.id): message for message in messages}


async def verified_sources(db, owner, sources: list[SourceMessage]) -> dict[str, SourceMessage]:
    by_id = await _messages_for(db, owner, [source.id for source in sources])
    verified = {}
    for source in sources:
        message = by_id.get(source.id)
        try:
            observed = datetime.fromisoformat(source.observed_at)
        except ValueError:
            continue
        if (
            message is not None
            and source.session_id == str(message.session_id)
            and source.text == message.content_markdown[:8000]
            and observed.tzinfo is not None
            and observed == message.created_at
        ):
            verified[source.id] = SourceMessage(
                id=str(message.id),
                session_id=str(message.session_id),
                text=message.content_markdown[:8000],
                observed_at=message.created_at.isoformat(),
            )
    return verified


def source_reference(source):
    return {
        "id": source.id,
        "session_id": source.session_id,
        "observed_at": source.observed_at,
        "digest": sha256(source.text.encode()).hexdigest(),
    }


async def verified_references(db, owner, refs):
    messages = await _messages_for(db, owner, [ref["id"] for ref in refs])
    verified = []
    for ref in refs:
        message = messages.get(ref["id"])
        if message is None:
            continue
        source = SourceMessage(
            id=str(message.id),
            session_id=str(message.session_id),
            observed_at=message.created_at.isoformat(),
            text=message.content_markdown[:8000],
        )
        if source_reference(source) == ref:
            verified.append(source)
    return verified
