"""Transactional memory policy. Model output is a proposal, never a database command."""

import re
import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import case, delete, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memory.automatic_models import (
    ConversationMemorySummary,
    MemoryTask,
    PersonalMemoryEvent,
    PersonalMemoryItem,
    PersonalMemoryState,
)
from app.modules.memory.contracts import ExtractionResponse, SourceMessage
from app.modules.memory.provenance import source_reference, verified_sources
from app.modules.memory.service import _bump_context_revision
from app.modules.memory.summaries import save_summary

SENSITIVE = re.compile(
    r"(?:密码|口令|身份证|银行卡|手机号|电话是|家庭住址|详细地址|诊断为|学校名称"
    r"|api[_ -]?key|bearer\s|sk-[\w-]+|[\w.+-]+@[\w.-]+\.[a-z]{2,}"
    r"|(?<!\d)1[3-9]\d{9}(?!\d)|\d{17}[\dXx])",
    re.I,
)
NON_PERSONAL = re.compile(
    r"(?:假设|假如|例如|举个例子|角色扮演|扮演|故事中|故事里|他说|她说|引用|```|<private>|不要记住|别记住)"
)


def utcnow():
    return datetime.now(UTC)


async def state_for(db: AsyncSession, owner: uuid.UUID, *, lock=False, create=True):
    if create:
        await db.execute(
            insert(PersonalMemoryState)
            .values(
                owner_user_id=owner,
                auto_enabled=True,
                use_enabled=True,
                revision=1,
                content_revision=0,
            )
            .on_conflict_do_nothing(index_elements=["owner_user_id"])
        )
    query = select(PersonalMemoryState).where(PersonalMemoryState.owner_user_id == owner)
    if lock:
        query = query.with_for_update()
    return await db.scalar(query.execution_options(populate_existing=True))


async def enqueue_run(db: AsyncSession, run, *, immediate=False):
    state = await state_for(db, run.owner_user_id, lock=True)
    if not state.auto_enabled:
        return
    await db.execute(
        insert(MemoryTask)
        .values(
            id=uuid.uuid4(),
            owner_user_id=run.owner_user_id,
            source_run_id=str(run.id),
            session_id=str(run.session_id),
            status="QUEUED",
            attempt=0,
            available_at=utcnow(),
            reason="BACKFILL" if immediate else None,
        )
        .on_conflict_do_nothing(index_elements=["owner_user_id", "source_run_id"])
    )


async def retract_context(db: AsyncSession, owner: uuid.UUID, state=None):
    state = state or await state_for(db, owner, lock=True)
    state.history_after = utcnow()
    await _bump_context_revision(db, owner)
    state.lease_token, state.lease_until = None, None
    await db.execute(
        delete(ConversationMemorySummary).where(ConversationMemorySummary.owner_user_id == owner)
    )
    await db.execute(
        update(MemoryTask)
        .where(
            MemoryTask.owner_user_id == owner,
            MemoryTask.status.in_(["QUEUED", "RUNNING", "RETRY_REQUIRED"]),
        )
        .values(status="CANCELLED", reason="MEMORY_CONTEXT_CHANGED")
    )


async def settings_update(
    db: AsyncSession, owner: uuid.UUID, base_revision: int, auto_enabled: bool, use_enabled: bool
):
    state = await state_for(db, owner, lock=True)
    if state.revision != base_revision:
        raise ValueError("记忆设置已变化，请刷新")
    if state.auto_enabled != auto_enabled or state.use_enabled != use_enabled:
        state.auto_enabled, state.use_enabled = auto_enabled, use_enabled
        state.revision += 1
        await retract_context(db, owner, state)
    await db.commit()


def item_dto(row):
    return {
        "id": str(row.id),
        "key": row.key,
        "category": row.category,
        "statement": row.statement,
        "status": row.status,
        "manual": row.manual,
        "revision": row.revision,
        "sources": row.sources,
        "valid_until": row.valid_until,
        "updated_at": row.updated_at,
    }


async def overview(db: AsyncSession, owner: uuid.UUID, query="", category=None, offset=0, limit=50):
    state = await state_for(db, owner, create=False)
    filters = [PersonalMemoryItem.owner_user_id == owner]
    if query:
        filters.append(PersonalMemoryItem.statement.icontains(query, autoescape=True))
    if category:
        filters.append(PersonalMemoryItem.category == category)
    rows = list(
        await db.scalars(
            select(PersonalMemoryItem)
            .where(*filters)
            .order_by(PersonalMemoryItem.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    total = await db.scalar(select(func.count()).select_from(PersonalMemoryItem).where(*filters))
    tasks = list(
        await db.scalars(
            select(MemoryTask)
            .where(MemoryTask.owner_user_id == owner)
            .order_by(MemoryTask.created_at.desc())
            .limit(100)
        )
    )
    now = utcnow()
    summary_rows = list(
        await db.scalars(
            select(PersonalMemoryItem)
            .where(PersonalMemoryItem.owner_user_id == owner, PersonalMemoryItem.status == "ACTIVE")
            .order_by(PersonalMemoryItem.updated_at.desc())
            .limit(200)
        )
    )
    active = [
        r
        for r in summary_rows
        if r.status == "ACTIVE" and (not r.valid_until or r.valid_until > now)
    ]
    return {
        "settings": {
            "auto_enabled": state.auto_enabled if state else True,
            "use_enabled": state.use_enabled if state else True,
            "revision": state.revision if state else 1,
        },
        "total": total or 0,
        "offset": offset,
        "has_more": offset + len(rows) < (total or 0),
        "content_revision": state.content_revision if state else 0,
        "last_updated_at": state.last_updated_at if state else None,
        "items": [item_dto(r) for r in rows],
        "summary_markdown": "\n".join(f"- {r.statement}" for r in active),
        "tasks": [
            {
                "id": str(t.id),
                "session_id": t.session_id,
                "status": t.status,
                "reason": t.reason,
                "attempt": t.attempt,
                "updated_at": t.updated_at,
            }
            for t in tasks
        ],
        "notice": (
            "自动记忆仅供个性化参考，不是测验成绩。"
            "遗忘会停止本地召回，不表示删除了 Knodo 的历史会话。"
        ),
    }


async def item_action(
    db: AsyncSession,
    owner: uuid.UUID,
    item_id: uuid.UUID,
    *,
    base_revision: int,
    action: str,
    statement: str | None = None,
):
    state = await state_for(db, owner, lock=True)
    row = await db.scalar(
        select(PersonalMemoryItem)
        .where(PersonalMemoryItem.id == item_id, PersonalMemoryItem.owner_user_id == owner)
        .with_for_update()
    )
    if row is None:
        raise LookupError("记忆不存在")
    if row.revision != base_revision:
        raise ValueError("记忆已被更新，请刷新")
    if action == "EDIT":
        if not statement or not 2 <= len(statement.strip()) <= 400:
            raise ValueError("请填写 2–400 字的记忆")
        row.statement, row.manual, row.status = statement.strip(), True, "ACTIVE"
    elif action == "FORGET":
        row.status = "REMOVED"
    elif action == "RESTORE":
        row.status, row.manual = "ACTIVE", True
    elif action == "ALLOW_AUTO":
        row.manual = False
    elif action == "CONFIRM":
        row.status, row.manual = "ACTIVE", True
    else:
        raise ValueError("不支持的记忆操作")
    row.revision += 1
    row.updated_at = utcnow()
    db.add(
        PersonalMemoryEvent(
            owner_user_id=owner,
            item_id=row.id,
            revision=row.revision,
            action=action,
            statement=row.statement,
        )
    )
    await retract_context(db, owner, state)
    await db.commit()
    return item_dto(row)


async def apply_extraction(
    db: AsyncSession, owner: uuid.UUID, response: ExtractionResponse, sources: list[SourceMessage]
):
    """Caller owns the account lease and transaction. Exact quote + provenance required."""
    state = await state_for(db, owner, lock=True)
    if not state.auto_enabled:
        return 0
    by_id = await verified_sources(db, owner, sources)
    protected = list(
        await db.scalars(
            select(PersonalMemoryItem).where(
                PersonalMemoryItem.owner_user_id == owner,
                (PersonalMemoryItem.status == "REMOVED") | PersonalMemoryItem.manual.is_(True),
            )
        )
    )
    blocked_sources = {ref["message_id"] for item in protected for ref in item.sources}
    # Unknown topic aliases require student confirmation after a personal correction.
    # Keyword matching alone cannot prove that a paraphrase is a different fact.
    changed = 0
    for fact in sorted(
        response.facts,
        key=lambda f: (
            by_id[f.source_message_id].observed_at if f.source_message_id in by_id else "",
            f.source_message_id,
        ),
    ):
        if fact.source_message_id in blocked_sources:
            continue
        source = by_id.get(fact.source_message_id)
        if (
            not source
            or fact.quote not in source.text
            or SENSITIVE.search(source.text)
            or SENSITIVE.search(fact.statement)
            or NON_PERSONAL.search(source.text)
        ):
            continue
        key = re.sub(r"\s+", "", fact.key.casefold())
        if not key or any(ord(c) < 32 for c in key):
            continue
        valid_until = None
        if fact.valid_until:
            try:
                valid_until = datetime.fromisoformat(fact.valid_until.replace("Z", "+00:00"))
                if valid_until.tzinfo is None:
                    continue
            except ValueError:
                continue
        observed = datetime.fromisoformat(source.observed_at)
        row = await db.scalar(
            select(PersonalMemoryItem).where(
                PersonalMemoryItem.owner_user_id == owner, PersonalMemoryItem.key == key
            )
        )
        if row is None:
            # Exact normalized statements share a single entry even if the extractor
            # varies its key. Do not guess that merely similar topics are equivalent.
            peers = await db.scalars(
                select(PersonalMemoryItem).where(
                    PersonalMemoryItem.owner_user_id == owner,
                    PersonalMemoryItem.category == fact.category,
                )
            )
            row = next(
                (p for p in peers if normalized(p.statement) == normalized(fact.statement)), None
            )
        provenance = {
            "message_id": source.id,
            "session_id": source.session_id,
            "observed_at": source.observed_at,
            "deleted": False,
        }
        if row and (row.status == "REMOVED" or row.manual):
            continue
        if row is None:
            row = PersonalMemoryItem(
                owner_user_id=owner,
                key=key,
                category=fact.category,
                statement=fact.statement,
                status=(
                    "ACTIVE" if fact.certainty == "EXPLICIT" and not protected else "CANDIDATE"
                ),
                manual=False,
                revision=1,
                sources=[provenance],
                observed_at=observed,
                valid_until=valid_until,
            )
            db.add(row)
            await db.flush()
            action = "AUTO_CREATE"
        else:
            if any(s["message_id"] == source.id for s in row.sources):
                continue
            refs = list(row.sources)
            if not any(s["message_id"] == source.id for s in refs):
                refs.append(provenance)
            if observed < row.observed_at or fact.certainty != "EXPLICIT":
                row.sources = refs[-100:]
                continue
            if fact.statement == row.statement and refs == row.sources:
                continue
            needs_review = bool(protected) and (
                row.status == "CANDIDATE" or normalized(fact.statement) != normalized(row.statement)
            )
            row.statement, row.sources = fact.statement, refs[-100:]
            row.category = fact.category
            row.status = "CANDIDATE" if needs_review else "ACTIVE"
            row.valid_until, row.observed_at = valid_until, observed
            row.revision += 1
            action = "AUTO_UPDATE"
        row.updated_at = utcnow()
        db.add(
            PersonalMemoryEvent(
                owner_user_id=owner,
                item_id=row.id,
                revision=row.revision,
                action=action,
                statement=row.statement,
            )
        )
        changed += 1
    if changed:
        state = await state_for(db, owner)
        state.content_revision += 1
        state.last_updated_at = utcnow()
    for summary in response.summaries:
        cited = [by_id.get(source_id) for source_id in summary.source_message_ids]
        if (
            not cited
            or any(
                source is None
                or source.session_id != summary.session_id
                or source.id in blocked_sources
                or SENSITIVE.search(source.text)
                for source in cited
            )
            or SENSITIVE.search(summary.summary)
        ):
            continue
        if protected or any(NON_PERSONAL.search(source.text) for source in cited):
            continue
        # A withdrawal cuts off old prose. Historical facts may still be processed,
        # but unchecked old summaries cannot carry them back into a teacher request.
        if state.history_after and any(
            datetime.fromisoformat(source.observed_at) <= state.history_after for source in cited
        ):
            continue
        source_ids = {source.id for source in cited}
        linked = list(
            await db.scalars(
                select(PersonalMemoryItem).where(
                    PersonalMemoryItem.owner_user_id == owner,
                )
            )
        )
        linked = [
            item for item in linked if any(ref["message_id"] in source_ids for ref in item.sources)
        ]
        if any(item.status != "ACTIVE" for item in linked):
            continue
        saved = await save_summary(
            db,
            owner,
            summary.session_id,
            {
                "text": summary.summary,
                "sources": [source_reference(source) for source in cited],
                "items": {str(item.id): item.revision for item in linked},
                "epoch": state.history_after.isoformat() if state.history_after else None,
            },
        )
        if saved:
            state.content_revision += 1
            state.last_updated_at = utcnow()
    return changed


class MemoryRetriever(Protocol):
    async def retrieve(
        self, db: AsyncSession, owner: uuid.UUID, query: str, limit: int
    ) -> list[dict]: ...


def terms(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9_]{2,}", text.lower()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        words.update(segment[i : i + 2] for i in range(len(segment) - 1))
    return words


def normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


PROFILE_QUERY = re.compile(r"我的?(?:兴趣|偏好|目标|计划|记忆)|之前.*(?:告诉|说)|结合我|关于我")
CATEGORY_QUERY = {
    "PREFERENCE": re.compile(r"讲解|解释|例子|偏好|图解|提示"),
    "INTEREST": re.compile(r"兴趣|爱好"),
    "GOAL": re.compile(r"目标"),
    "PLAN": re.compile(r"计划|安排"),
}


class KeywordMemoryRetriever:
    async def retrieve(self, db, owner, query, limit=6):
        limit = min(max(int(limit), 0), 6)
        state = await state_for(db, owner, create=False)
        if not limit or (state and not state.use_enabled):
            return []
        tokens = set(sorted(terms(query[:1000]))[:64])
        profile_query = bool(PROFILE_QUERY.search(query))
        matches = [
            PersonalMemoryItem.statement.icontains(t, autoescape=True)
            | PersonalMemoryItem.key.icontains(t, autoescape=True)
            for t in sorted(tokens)
        ]
        categories = [c for c, pattern in CATEGORY_QUERY.items() if pattern.search(query)]
        metadata = PersonalMemoryItem.category.in_(categories)
        clauses = [
            PersonalMemoryItem.owner_user_id == owner,
            PersonalMemoryItem.status == "ACTIVE",
            (PersonalMemoryItem.valid_until.is_(None))
            | (PersonalMemoryItem.valid_until > utcnow()),
        ]
        # Filter in SQL before ranking, so recent unrelated rows cannot crowd out
        # an older relevant row beyond a fixed preselection window.
        if not profile_query:
            if not matches and not categories:
                return []
            clauses.append(or_(*matches, metadata))
        relevance = sum((case((match, 1), else_=0) for match in matches), literal(0))
        rows = await db.scalars(
            select(PersonalMemoryItem)
            .where(*clauses)
            .order_by(
                relevance.desc(),
                metadata.desc(),
                PersonalMemoryItem.manual.desc(),
                PersonalMemoryItem.observed_at.desc(),
                PersonalMemoryItem.id.desc(),
            )
            .limit(limit)
        )
        return [
            {
                "id": f"personal-memory:{r.id}:v{r.revision}",
                "source": "USER_EDITED" if r.manual else "AUTO_SUMMARIZED",
                "summary": r.statement[:400],
            }
            for r in rows
        ]


async def history_backfill(db: AsyncSession, owner: uuid.UUID, session_ids: list[uuid.UUID]):
    from app.modules.teaching.models import AgentRun, LessonSession

    state = await state_for(db, owner, lock=True)
    if not state.auto_enabled:
        raise ValueError("请先开启自动整理")
    owned = set(
        await db.scalars(
            select(LessonSession.id).where(
                LessonSession.owner_user_id == owner, LessonSession.id.in_(session_ids)
            )
        )
    )
    if owned != set(session_ids):
        raise LookupError("会话不存在")
    runs = list(
        await db.scalars(
            select(AgentRun)
            .where(
                AgentRun.owner_user_id == owner,
                AgentRun.session_id.in_(session_ids),
                AgentRun.status == "SUCCEEDED",
            )
            .order_by(AgentRun.created_at)
        )
    )
    added = 0
    for start in range(0, len(runs), 200):
        values = [
            dict(
                id=uuid.uuid4(),
                owner_user_id=owner,
                source_run_id=str(run.id),
                session_id=str(run.session_id),
                status="QUEUED",
                attempt=0,
                available_at=utcnow(),
                reason="BACKFILL",
            )
            for run in runs[start : start + 200]
        ]
        inserted = await db.scalars(
            insert(MemoryTask)
            .values(values)
            .on_conflict_do_update(
                index_elements=["owner_user_id", "source_run_id"],
                set_={
                    "status": "QUEUED",
                    "reason": "BACKFILL",
                    "lease_token": None,
                    "available_at": utcnow(),
                    "updated_at": utcnow(),
                },
                where=MemoryTask.status == "CANCELLED",
            )
            .returning(MemoryTask.id)
        )
        added += len(list(inserted))
    await db.commit()
    return {
        "accepted_runs": added,
        "skipped_runs": len(runs) - added,
        "notice": "重复来源会自动跳过，已遗忘的记忆不会恢复。",
    }


async def delete_chat_memory(
    db: AsyncSession, owner: uuid.UUID, session_id: uuid.UUID, forget: bool
):
    state = await state_for(db, owner, lock=True)
    await db.execute(
        update(MemoryTask)
        .where(
            MemoryTask.owner_user_id == owner,
            MemoryTask.session_id == str(session_id),
            MemoryTask.status.in_(["QUEUED", "RUNNING", "RETRY_REQUIRED"]),
        )
        .values(status="CANCELLED", reason="SOURCE_DELETED")
    )
    await db.execute(
        delete(ConversationMemorySummary).where(
            ConversationMemorySummary.owner_user_id == owner,
            ConversationMemorySummary.session_id == str(session_id),
        )
    )
    rows = list(
        await db.scalars(
            select(PersonalMemoryItem).where(PersonalMemoryItem.owner_user_id == owner)
        )
    )
    changed = False
    for row in rows:
        if not any(s["session_id"] == str(session_id) for s in row.sources):
            continue
        row.sources = [
            {**s, "deleted": True} if s["session_id"] == str(session_id) else s for s in row.sources
        ]
        if forget and not row.manual and row.status != "REMOVED":
            row.status = "REMOVED"
            row.revision += 1
            db.add(
                PersonalMemoryEvent(
                    owner_user_id=owner,
                    item_id=row.id,
                    revision=row.revision,
                    action="CHAT_FORGET",
                    statement=row.statement,
                )
            )
            changed = True
    if changed:
        await retract_context(db, owner, state)
