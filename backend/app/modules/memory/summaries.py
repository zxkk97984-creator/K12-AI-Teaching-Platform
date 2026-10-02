"""Versioned summary provenance; unchecked legacy prose is never recalled."""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.modules.memory.automatic_models import ConversationMemorySummary, PersonalMemoryItem
from app.modules.memory.provenance import verified_references

FORMAT = "k12.local-summary.v1"


def decode(content):
    try:
        value = json.loads(content)
        if value.get("format") == FORMAT and isinstance(value.get("sections"), list):
            return [
                section
                for section in value["sections"][-20:]
                if isinstance(section, dict)
                and isinstance(section.get("text"), str)
                and isinstance(section.get("sources"), list)
                and 1 <= len(section["sources"]) <= 20
                and all(
                    isinstance(ref, dict)
                    and all(
                        isinstance(ref.get(k), str)
                        for k in ("id", "session_id", "observed_at", "digest")
                    )
                    for ref in section["sources"]
                )
                and isinstance(section.get("items"), dict)
                and all(
                    isinstance(k, str) and isinstance(v, int) and v > 0
                    for k, v in section["items"].items()
                )
            ]
    except (ValueError, TypeError, AttributeError):
        pass
    return []


async def save_summary(db, owner, session_id, section):
    previous = await db.scalar(
        select(ConversationMemorySummary).where(
            ConversationMemorySummary.owner_user_id == owner,
            ConversationMemorySummary.session_id == session_id,
        )
    )
    sections = decode(previous.content) if previous else []
    # A replay of the same source batch is idempotent, even if the model rephrases it.
    source_ids = {s["id"] for s in section["sources"]}
    if any({s["id"] for s in old["sources"]} == source_ids for old in sections):
        return False
    sections.append(section)
    content = json.dumps({"format": FORMAT, "sections": sections[-20:]}, ensure_ascii=False)
    await db.execute(
        insert(ConversationMemorySummary)
        .values(
            id=uuid.uuid4(), owner_user_id=owner, session_id=session_id, content=content, revision=1
        )
        .on_conflict_do_update(
            index_elements=["owner_user_id", "session_id"],
            set_={
                "content": content,
                "revision": ConversationMemorySummary.revision + 1,
                "updated_at": datetime.now(UTC),
            },
        )
    )
    return True


async def recall_summary(db, owner, session_id, state, now):
    if state and not state.use_enabled:
        return None
    # Model prose cannot reliably distinguish paraphrases of withdrawn/corrected facts.
    protected = await db.scalar(
        select(PersonalMemoryItem.id)
        .where(
            PersonalMemoryItem.owner_user_id == owner,
            (PersonalMemoryItem.manual.is_(True)) | (PersonalMemoryItem.status == "REMOVED"),
        )
        .limit(1)
    )
    if protected:
        return None
    row = await db.scalar(
        select(ConversationMemorySummary).where(
            ConversationMemorySummary.owner_user_id == owner,
            ConversationMemorySummary.session_id == str(session_id),
        )
    )
    if not row:
        return None
    texts = []
    for section in decode(row.content):
        try:
            sources = section["sources"]
            if (
                not sources
                or section["epoch"]
                != (state.history_after.isoformat() if state and state.history_after else None)
                or any(s["session_id"] != str(session_id) for s in sources)
            ):
                continue
            verified = await verified_references(db, owner, sources)
            if len(verified) != len(sources):
                continue
            versions = section["items"]
            items = list(
                await db.scalars(
                    select(PersonalMemoryItem).where(
                        PersonalMemoryItem.owner_user_id == owner,
                        PersonalMemoryItem.id.in_([uuid.UUID(i) for i in versions]),
                    )
                )
            )
            if len(items) != len(versions) or any(
                i.status != "ACTIVE"
                or i.revision != versions[str(i.id)]
                or (i.valid_until and i.valid_until <= now)
                for i in items
            ):
                continue
            text = section["text"]
            if isinstance(text, str) and text.strip():
                texts.append(text[:1200])
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    if not texts:
        return None
    return {
        "id": f"session-summary:{row.id}:v{row.revision}",
        "source": "SESSION_SUMMARY",
        "summary": "\n".join(texts)[-2400:],
    }
