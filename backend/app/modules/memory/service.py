"""Memory candidate state machine and learner-context assembly (T18 K2/K3/K5/K10).

Nothing here is written by a model. Candidates are produced by two explicit,
deterministic rules over already-projected evidence; every later transition is
an action by the owning student. ``memory_events`` is append-only, so an edit
keeps the previous statement and a forgotten candidate is terminal: because the
derivation key stays unique per (owner, rule), replaying the same old evidence —
or even accumulating new evidence — can never re-create a candidate the student
has forgotten.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import CORRECT_OUTCOMES, EvidenceItem
from app.modules.learning.projection import evidence_context
from app.modules.memory.models import (
    DERIVATION_RULE_VERSION,
    DOCUMENT_CATEGORIES,
    MEMORY_ACTIONS,
    MemoryCandidate,
    MemoryContextState,
    MemoryDocument,
    MemoryDocumentVersion,
    MemoryEvent,
)

MAX_CONTEXT_EVIDENCE = 12
STATEMENT_MIN = 2
STATEMENT_MAX = 400
DOCUMENT_TITLE_MAX = 80
DOCUMENT_CONTENT_MAX = 20_000

LOCAL_WITHDRAWAL_NOTICE = (
    "本地已遗忘：不再注入教学上下文。当前版本没有远端记忆同步，因此不存在远端副本；"
    "若将来接入平台侧记忆，需要按平台能力单独发起撤回，本状态不宣称物理清除了其它系统里的记录。"
)
DISPUTED_NOTICE = "你标记为有疑问：在确认或修改之前，不再作为教学依据。"
ACTIVE_NOTICE = "你已确认：可以作为教学参考，仍可随时质疑、修改或遗忘。"


class MemoryNotFound(Exception):
    """No such memory for this owner (also used for another student's row)."""


class MemoryRevisionConflict(Exception):
    """The client acted on a stale revision; nothing was written."""


class MemoryTransitionInvalid(Exception):
    """The requested action is not legal from the current status."""


class MemoryForgotten(Exception):
    """A forgotten memory is terminal and cannot be changed again."""


class MemoryDocumentNotFound(Exception):
    """No document or version belongs to this owner."""


class MemoryDocumentRevisionConflict(Exception):
    """The document changed after the client read it."""


class MemoryDocumentValidation(Exception):
    """Document title/category/content failed local validation."""


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _rule_candidates(items: list[EvidenceItem]) -> list[dict[str, Any]]:
    """Two conservative strategy rules over the student's own evidence."""

    candidates: list[dict[str, Any]] = []
    answers = [item for item in items if item.source_kind == "QUIZ_ANSWERED"]
    hints = [item for item in items if item.source_kind == "QUIZ_HINT_VIEWED"]

    by_question: dict[str, list[EvidenceItem]] = {}
    for item in sorted(answers, key=lambda row: row.observed_at):
        question = str((item.source_ref or {}).get("question_id") or "")
        if question:
            by_question.setdefault(question, []).append(item)

    for question, rows in by_question.items():
        first_wrong = next((row for row in rows if row.outcome not in CORRECT_OUTCOMES), None)
        later_correct = None
        if first_wrong is not None:
            later_correct = next(
                (
                    row
                    for row in rows
                    if row.outcome in CORRECT_OUTCOMES and row.observed_at > first_wrong.observed_at
                ),
                None,
            )
        if first_wrong is not None and later_correct is not None:
            candidates.append(
                {
                    "kind": "STUDY_STRATEGY",
                    "rule": "RETRY_AFTER_MISTAKE",
                    "statement": "答错后愿意再试一次：你在同一道题上从答错改到了答对。",
                    "content": {
                        "strategy": "RETRY_AFTER_MISTAKE",
                        "question_id": question,
                        "rule": "RETRY_AFTER_MISTAKE",
                    },
                    "basis_evidence_ids": [str(first_wrong.id), str(later_correct.id)],
                    "basis_counts": {"attempts_on_question": len(rows)},
                }
            )
            break

    hints_by_objective: dict[str, list[EvidenceItem]] = {}
    for item in hints:
        if item.objective_id:
            hints_by_objective.setdefault(item.objective_id, []).append(item)
    for objective, hint_rows in sorted(hints_by_objective.items()):
        first_hint = min(hint_rows, key=lambda row: row.observed_at)
        later_correct = next(
            (
                item
                for item in sorted(answers, key=lambda row: row.observed_at)
                if item.objective_id == objective
                and item.outcome in CORRECT_OUTCOMES
                and item.observed_at > first_hint.observed_at
            ),
            None,
        )
        if later_correct is not None:
            candidates.append(
                {
                    "kind": "STUDY_STRATEGY",
                    "rule": "HINT_THEN_CORRECT",
                    "statement": "遇到难题时会先看提示，再自己完成作答。",
                    "content": {
                        "strategy": "HINT_THEN_CORRECT",
                        "objective_id": objective,
                        "rule": "HINT_THEN_CORRECT",
                    },
                    "basis_evidence_ids": [str(first_hint.id), str(later_correct.id)],
                    "basis_counts": {"hints_viewed": len(hint_rows)},
                }
            )
            break

    return candidates


async def derive_candidates(
    db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int = 200
) -> dict[str, int]:
    """Derive memory candidates; a forgotten candidate is never re-created."""

    items = list(
        await db.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.owner_user_id == owner_user_id)
            .order_by(EvidenceItem.observed_at)
            .limit(limit)
        )
    )
    created = 0
    skipped = 0
    for candidate in _rule_candidates(items):
        derivation_key = f"{candidate['rule']}:{DERIVATION_RULE_VERSION}"[:96]
        statement = str(candidate["statement"])[:STATEMENT_MAX]
        statement_id = await db.scalar(
            pg_insert(MemoryCandidate)
            .values(
                id=uuid.uuid4(),
                owner_user_id=owner_user_id,
                kind=candidate["kind"],
                status="CANDIDATE",
                statement=statement,
                content=candidate["content"],
                basis_evidence_ids=candidate["basis_evidence_ids"],
                basis_counts=candidate["basis_counts"],
                derivation_key=derivation_key,
                origin="RULE_DERIVED",
                derivation_rule_version=DERIVATION_RULE_VERSION,
                revision=1,
            )
            .on_conflict_do_nothing(index_elements=["owner_user_id", "derivation_key"])
            .returning(MemoryCandidate.id)
        )
        if statement_id is None:
            # Includes the REMOVED case: a forgotten suggestion stays forgotten.
            skipped += 1
            continue
        db.add(
            MemoryEvent(
                candidate_id=statement_id,
                owner_user_id=owner_user_id,
                action="CREATE",
                from_status="NONE",
                to_status="CANDIDATE",
                from_revision=0,
                to_revision=1,
                statement_before=None,
                statement_after=statement,
                reason=None,
                actor="STUDENT",
            )
        )
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped, "rule_version": DERIVATION_RULE_VERSION}


def _event_dto(row: MemoryEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "action": row.action,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "from_revision": row.from_revision,
        "to_revision": row.to_revision,
        "statement_before": row.statement_before,
        "statement_after": row.statement_after,
        "reason": row.reason,
        "actor": row.actor,
        "created_at": row.created_at.isoformat(),
    }


def memory_dto(row: MemoryCandidate, history: list[MemoryEvent] | None = None) -> dict[str, Any]:
    if row.status == "ACTIVE":
        injection = "INJECTED"
        note = ACTIVE_NOTICE
    elif row.status == "CANDIDATE":
        injection = "EXCLUDED"
        note = "这是系统建议的候选记忆，只有你确认后才会作为教学参考。"
    elif row.status == "DISPUTED":
        injection = "EXCLUDED"
        note = DISPUTED_NOTICE
    else:
        injection = "EXCLUDED"
        note = LOCAL_WITHDRAWAL_NOTICE
    return {
        "id": str(row.id),
        "kind": row.kind,
        "status": row.status,
        "statement": row.statement,
        "content": dict(row.content or {}),
        "basis_evidence_ids": list(row.basis_evidence_ids or []),
        "basis_counts": dict(row.basis_counts or {}),
        "rule_version": row.derivation_rule_version,
        "origin": row.origin,
        "revision": row.revision,
        "injection_status": injection,
        "injection_note": note,
        "local_withdrawal_notice": LOCAL_WITHDRAWAL_NOTICE if row.status == "REMOVED" else None,
        "remote_residue": "NONE_LOCAL_ONLY",
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "removed_at": row.removed_at.isoformat() if row.removed_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "history": [_event_dto(event) for event in (history or [])],
    }


async def history_for(db: AsyncSession, *, candidate_id: uuid.UUID) -> list[MemoryEvent]:
    rows = await db.scalars(
        select(MemoryEvent)
        .where(MemoryEvent.candidate_id == candidate_id)
        .order_by(MemoryEvent.created_at, MemoryEvent.to_revision)
    )
    return list(rows)


async def list_memories(db: AsyncSession, *, owner_user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(MemoryCandidate)
        .where(MemoryCandidate.owner_user_id == owner_user_id)
        .order_by(MemoryCandidate.updated_at.desc())
    )
    return [memory_dto(row) for row in rows]


async def memory_detail(
    db: AsyncSession, *, owner_user_id: uuid.UUID, memory_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await db.scalar(
        select(MemoryCandidate).where(
            MemoryCandidate.id == memory_id, MemoryCandidate.owner_user_id == owner_user_id
        )
    )
    if row is None:
        return None
    return memory_dto(row, await history_for(db, candidate_id=row.id))


async def apply_memory_event(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    memory_id: uuid.UUID,
    action: str,
    base_revision: int,
    statement: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """One student action, one transaction: revision check first, then write."""

    if action not in MEMORY_ACTIONS:
        raise MemoryTransitionInvalid("不支持的记忆操作")
    row = await db.scalar(
        select(MemoryCandidate)
        .where(MemoryCandidate.id == memory_id, MemoryCandidate.owner_user_id == owner_user_id)
        .with_for_update()
    )
    if row is None:
        await db.rollback()
        raise MemoryNotFound("记忆不存在")
    if row.status == "REMOVED":
        await db.rollback()
        raise MemoryForgotten("这条记忆已被遗忘，不能再次修改")
    if row.revision != base_revision:
        # Stale write: nothing is changed, not even partially.
        await db.rollback()
        raise MemoryRevisionConflict("这条记忆已被更新，请刷新后重试")

    from_status = row.status
    from_revision = row.revision
    statement_before = row.statement
    statement_after = row.statement
    new_status = row.status
    now = datetime.now(UTC)

    if action == "CONFIRM":
        if row.status not in ("CANDIDATE", "DISPUTED"):
            await db.rollback()
            raise MemoryTransitionInvalid("当前状态不能再确认")
        new_status = "ACTIVE"
        row.decided_at = now
    elif action == "DISPUTE":
        if row.status not in ("CANDIDATE", "ACTIVE"):
            await db.rollback()
            raise MemoryTransitionInvalid("当前状态不能标记为有疑问")
        new_status = "DISPUTED"
    elif action == "EDIT":
        cleaned = (statement or "").strip()
        if not (STATEMENT_MIN <= len(cleaned) <= STATEMENT_MAX):
            await db.rollback()
            raise MemoryTransitionInvalid(
                f"修改后的内容需要 {STATEMENT_MIN}-{STATEMENT_MAX} 个字符"
            )
        statement_after = cleaned
    else:  # FORGET
        new_status = "REMOVED"
        row.removed_at = now

    row.status = new_status
    row.statement = statement_after
    row.revision = from_revision + 1
    row.updated_at = now
    db.add(
        MemoryEvent(
            candidate_id=row.id,
            owner_user_id=owner_user_id,
            action=action,
            from_status=from_status,
            to_status=new_status,
            from_revision=from_revision,
            to_revision=row.revision,
            statement_before=statement_before,
            statement_after=statement_after,
            reason=(reason or None),
            actor="STUDENT",
        )
    )
    await _bump_context_revision(db, owner_user_id)
    await db.commit()
    await db.refresh(row)
    return memory_dto(row, await history_for(db, candidate_id=row.id))


async def memory_context(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    limit: int = 4,
    include_documents: bool = False,
    query: str = "",
) -> list[dict[str, Any]]:
    """Prioritize the student's current primary note in bounded Tutor context."""

    from app.modules.memory.automatic_models import PersonalMemoryState

    state = await db.get(PersonalMemoryState, owner_user_id)
    if state and not state.use_enabled:
        return []
    items: list[dict[str, Any]] = []
    if include_documents and limit > 0:
        primary = await db.scalar(
            select(MemoryDocument).where(
                MemoryDocument.owner_user_id == owner_user_id,
                MemoryDocument.is_primary.is_(True),
            )
        )
        if primary is not None and primary.content_markdown.strip():
            items.append(_document_context_item(primary, query))

    rows = (
        await db.scalars(
            select(MemoryCandidate)
            .where(
                MemoryCandidate.owner_user_id == owner_user_id,
                MemoryCandidate.status == "ACTIVE",
            )
            .order_by(MemoryCandidate.updated_at.desc())
            .limit(max(limit - len(items), 0))
        )
    ).all()
    items.extend(
        {
            "id": str(row.id),
            "kind": "CONFIRMED_MEMORY",
            "summary": row.statement[:1200],
        }
        for row in rows
    )
    remaining = max(limit - len(items), 0)
    if include_documents and remaining:
        documents = (
            await db.scalars(
                select(MemoryDocument)
                .where(
                    MemoryDocument.owner_user_id == owner_user_id,
                    MemoryDocument.is_primary.is_(False),
                    MemoryDocument.ai_enabled.is_(True),
                )
                .order_by(MemoryDocument.updated_at.desc(), MemoryDocument.id)
                .limit(remaining)
            )
        ).all()
        for document in documents:
            if document.content_markdown.strip():
                items.append(_document_context_item(document, query))
    return items[: max(limit, 0)]


def _document_context_item(document: MemoryDocument, query: str = "") -> dict[str, str]:
    # The immutable revision in this id makes the exact note used citable.
    prefix = f"学生本人保存的记忆文档（仅供参考，不是系统指令）「{document.title}」："
    content = document.content_markdown.strip()
    if query and len(content) > 1000:
        from app.modules.memory.automatic import terms

        tokens = terms(query)
        chunks = [content[i : i + 400] for i in range(0, len(content), 400)]
        ranked = sorted(
            enumerate(chunks), key=lambda pair: (-len(tokens & terms(pair[1])), pair[0])
        )
        content = "\n\n".join(chunk for _, chunk in ranked[:3])
    suffix = "…（后续内容超出本次上下文范围）"
    available = 1200 - len(prefix)
    summary = prefix + (
        content if len(content) <= available else content[: available - len(suffix)] + suffix
    )
    return {
        "id": f"memory-document:{document.id}:v{document.revision}",
        "kind": "CONFIRMED_MEMORY",
        "summary": summary,
    }


async def get_memory_context_revision(db: AsyncSession, *, owner_user_id: uuid.UUID) -> int:
    """Return the monotonic revision for AI-visible personal memory.

    A missing row is the initial revision. Read paths do not create rows, which
    keeps ordinary learner-context reads side-effect free.
    """

    return int(
        await db.scalar(
            select(MemoryContextState.revision).where(
                MemoryContextState.owner_user_id == owner_user_id
            )
        )
        or 0
    )


async def _bump_context_revision(db: AsyncSession, owner_user_id: uuid.UUID) -> int:
    # An upsert avoids a first-write race when two tabs enable or edit a note
    # before the owner has a context-state row.
    revision = await db.scalar(
        pg_insert(MemoryContextState)
        .values(owner_user_id=owner_user_id, revision=1)
        .on_conflict_do_update(
            index_elements=["owner_user_id"],
            set_={
                "revision": MemoryContextState.revision + 1,
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(MemoryContextState.revision)
    )
    if revision is None:  # pragma: no cover - PostgreSQL always returns the row
        raise RuntimeError("memory context revision upsert returned no row")
    from sqlalchemy import delete, update

    from app.modules.memory.automatic_models import (
        ConversationMemorySummary,
        MemoryTask,
        PersonalMemoryState,
    )

    await db.execute(
        pg_insert(PersonalMemoryState)
        .values(
            owner_user_id=owner_user_id,
            auto_enabled=True,
            use_enabled=True,
            revision=1,
            content_revision=0,
        )
        .on_conflict_do_nothing(index_elements=["owner_user_id"])
    )
    await db.execute(
        update(PersonalMemoryState)
        .where(PersonalMemoryState.owner_user_id == owner_user_id)
        .values(
            history_after=datetime.now(UTC),
            content_revision=PersonalMemoryState.content_revision + 1,
        )
    )
    await db.execute(
        delete(ConversationMemorySummary).where(
            ConversationMemorySummary.owner_user_id == owner_user_id
        )
    )
    await db.execute(
        update(MemoryTask)
        .where(
            MemoryTask.owner_user_id == owner_user_id,
            MemoryTask.status.in_(["QUEUED", "RUNNING", "RETRY_REQUIRED"]),
        )
        .values(status="CANCELLED", reason="MEMORY_CONTEXT_CHANGED")
    )
    return int(revision)


async def build_learner_context(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    evidence_limit: int = 6,
    memory_limit: int = 4,
    query: str = "",
) -> list[dict[str, str]]:
    """Bounded Tutor context: valid evidence, the primary note and opted-in notes."""

    items = await evidence_context(db, owner_user_id=owner_user_id, limit=evidence_limit)
    items += await memory_context(
        db,
        owner_user_id=owner_user_id,
        limit=memory_limit,
        include_documents=True,
        query=query,
    )
    merged: dict[str, dict[str, str]] = {}
    for item in items:
        merged.setdefault(item["id"], item)
    return list(merged.values())[:MAX_CONTEXT_EVIDENCE]


def _document_values(*, title: str, category: str, content_markdown: str) -> tuple[str, str, str]:
    cleaned_title = " ".join(title.split()).strip()
    cleaned_content = content_markdown.replace("\x00", "").strip()
    if not (1 <= len(cleaned_title) <= DOCUMENT_TITLE_MAX):
        raise MemoryDocumentValidation("标题需要 1-80 个字符")
    if category not in DOCUMENT_CATEGORIES:
        raise MemoryDocumentValidation("不支持的文档分类")
    if len(cleaned_content) > DOCUMENT_CONTENT_MAX:
        raise MemoryDocumentValidation("文档内容不能超过 20000 个字符")
    return cleaned_title, category, cleaned_content


def _document_dto(row: MemoryDocument, *, content: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(row.id),
        "title": row.title,
        "is_primary": row.is_primary,
        "category": row.category,
        "revision": row.revision,
        "ai_enabled": row.ai_enabled,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }
    if content:
        body["content_markdown"] = row.content_markdown
    return body


def _document_version_dto(row: MemoryDocumentVersion, *, content: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(row.id),
        "document_id": str(row.document_id),
        "revision": row.revision,
        "title": row.title,
        "category": row.category,
        "action": row.action,
        "created_at": row.created_at.isoformat(),
    }
    if content:
        body["content_markdown"] = row.content_markdown
    return body


async def list_documents(db: AsyncSession, *, owner_user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(MemoryDocument)
            .where(MemoryDocument.owner_user_id == owner_user_id)
            .order_by(MemoryDocument.updated_at.desc(), MemoryDocument.id)
        )
    ).all()
    return [_document_dto(row, content=False) for row in rows]


async def get_document(
    db: AsyncSession, *, owner_user_id: uuid.UUID, document_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await db.scalar(
        select(MemoryDocument).where(
            MemoryDocument.id == document_id, MemoryDocument.owner_user_id == owner_user_id
        )
    )
    if row is None:
        return None
    versions = (
        await db.scalars(
            select(MemoryDocumentVersion)
            .where(MemoryDocumentVersion.document_id == row.id)
            .order_by(MemoryDocumentVersion.revision.desc())
        )
    ).all()
    result = _document_dto(row)
    result["versions"] = [_document_version_dto(version, content=False) for version in versions]
    return result


async def create_document(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    title: str,
    category: str,
    content_markdown: str = "",
    ai_enabled: bool = False,
    is_primary: bool = False,
) -> dict[str, Any]:
    cleaned_title, cleaned_category, cleaned_content = _document_values(
        title=title, category=category, content_markdown=content_markdown
    )
    if is_primary:
        existing = await db.scalar(
            select(MemoryDocument).where(
                MemoryDocument.owner_user_id == owner_user_id,
                MemoryDocument.is_primary.is_(True),
            )
        )
        if existing is not None:
            return await get_document(db, owner_user_id=owner_user_id, document_id=existing.id)
        if cleaned_title != "个人记忆.md" or cleaned_category != "NOTE":
            raise MemoryDocumentValidation("主文档必须是个人记忆.md")
    if is_primary:
        inserted_id = await db.scalar(
            pg_insert(MemoryDocument)
            .values(
                id=uuid.uuid4(),
                owner_user_id=owner_user_id,
                title=cleaned_title,
                is_primary=True,
                category=cleaned_category,
                content_markdown=cleaned_content,
                revision=1,
                ai_enabled=True,
            )
            .on_conflict_do_nothing(
                index_elements=[MemoryDocument.owner_user_id],
                index_where=text("is_primary"),
            )
            .returning(MemoryDocument.id)
        )
        if inserted_id is None:
            existing = await db.scalar(
                select(MemoryDocument).where(
                    MemoryDocument.owner_user_id == owner_user_id,
                    MemoryDocument.is_primary.is_(True),
                )
            )
            if existing is None:
                raise MemoryDocumentValidation("主文档创建冲突，请重试")
            return await get_document(db, owner_user_id=owner_user_id, document_id=existing.id)
        row = await db.get(MemoryDocument, inserted_id)
    else:
        row = MemoryDocument(
            owner_user_id=owner_user_id,
            title=cleaned_title,
            is_primary=False,
            category=cleaned_category,
            content_markdown=cleaned_content,
            revision=1,
            ai_enabled=bool(ai_enabled),
        )
        db.add(row)
        await db.flush()
    db.add(
        MemoryDocumentVersion(
            document_id=row.id,
            owner_user_id=owner_user_id,
            revision=1,
            title=cleaned_title,
            category=cleaned_category,
            content_markdown=cleaned_content,
            action="CREATE",
        )
    )
    if row.ai_enabled:
        await _bump_context_revision(db, owner_user_id)
    await db.commit()
    await db.refresh(row)
    return await get_document(db, owner_user_id=owner_user_id, document_id=row.id) or _document_dto(
        row
    )


async def update_document(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    document_id: uuid.UUID,
    base_revision: int,
    title: str | None = None,
    category: str | None = None,
    content_markdown: str | None = None,
    ai_enabled: bool | None = None,
) -> dict[str, Any]:
    row = await db.scalar(
        select(MemoryDocument)
        .where(MemoryDocument.id == document_id, MemoryDocument.owner_user_id == owner_user_id)
        .with_for_update()
    )
    if row is None:
        await db.rollback()
        raise MemoryDocumentNotFound("文档不存在")
    if row.revision != base_revision:
        await db.rollback()
        raise MemoryDocumentRevisionConflict("文档已被更新，请刷新后重试")

    old_ai_enabled = row.ai_enabled
    new_title = title if title is not None else row.title
    new_category = category if category is not None else row.category
    new_content = content_markdown if content_markdown is not None else row.content_markdown
    cleaned_title, cleaned_category, cleaned_content = _document_values(
        title=new_title, category=new_category, content_markdown=new_content
    )
    if row.is_primary and ai_enabled is False:
        await db.rollback()
        raise MemoryDocumentValidation("个人记忆主文档供 AI 教师参考，不能在文档接口中关闭")
    new_ai_enabled = (
        True if row.is_primary else (old_ai_enabled if ai_enabled is None else bool(ai_enabled))
    )
    changed = (
        cleaned_title != row.title
        or cleaned_category != row.category
        or cleaned_content != row.content_markdown
        or new_ai_enabled != old_ai_enabled
    )
    if not changed:
        await db.rollback()
        return await get_document(
            db, owner_user_id=owner_user_id, document_id=row.id
        ) or _document_dto(row)

    row.title = cleaned_title
    row.category = cleaned_category
    row.content_markdown = cleaned_content
    row.ai_enabled = new_ai_enabled
    row.revision += 1
    row.updated_at = datetime.now(UTC)
    action = (
        "AI_USAGE" if title is None and category is None and content_markdown is None else "EDIT"
    )
    db.add(
        MemoryDocumentVersion(
            document_id=row.id,
            owner_user_id=owner_user_id,
            revision=row.revision,
            title=row.title,
            category=row.category,
            content_markdown=row.content_markdown,
            action=action,
        )
    )
    if old_ai_enabled or new_ai_enabled:
        await _bump_context_revision(db, owner_user_id)
    await db.commit()
    await db.refresh(row)
    return await get_document(db, owner_user_id=owner_user_id, document_id=row.id) or _document_dto(
        row
    )


async def list_document_versions(
    db: AsyncSession, *, owner_user_id: uuid.UUID, document_id: uuid.UUID
) -> list[dict[str, Any]]:
    exists = await db.scalar(
        select(MemoryDocument.id).where(
            MemoryDocument.id == document_id, MemoryDocument.owner_user_id == owner_user_id
        )
    )
    if exists is None:
        raise MemoryDocumentNotFound("文档不存在")
    rows = (
        await db.scalars(
            select(MemoryDocumentVersion)
            .where(
                MemoryDocumentVersion.document_id == document_id,
                MemoryDocumentVersion.owner_user_id == owner_user_id,
            )
            .order_by(MemoryDocumentVersion.revision.desc())
        )
    ).all()
    return [_document_version_dto(row, content=False) for row in rows]


async def get_document_version(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    document_id: uuid.UUID,
    revision: int,
) -> dict[str, Any]:
    row = await db.scalar(
        select(MemoryDocumentVersion).where(
            MemoryDocumentVersion.document_id == document_id,
            MemoryDocumentVersion.owner_user_id == owner_user_id,
            MemoryDocumentVersion.revision == revision,
        )
    )
    if row is None:
        raise MemoryDocumentNotFound("文档版本不存在")
    return _document_version_dto(row)


async def restore_document(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    document_id: uuid.UUID,
    version_revision: int,
    base_revision: int,
) -> dict[str, Any]:
    row = await db.scalar(
        select(MemoryDocument)
        .where(MemoryDocument.id == document_id, MemoryDocument.owner_user_id == owner_user_id)
        .with_for_update()
    )
    if row is None:
        await db.rollback()
        raise MemoryDocumentNotFound("文档不存在")
    if row.revision != base_revision:
        await db.rollback()
        raise MemoryDocumentRevisionConflict("文档已被更新，请刷新后重试")
    version = await db.scalar(
        select(MemoryDocumentVersion).where(
            MemoryDocumentVersion.document_id == document_id,
            MemoryDocumentVersion.owner_user_id == owner_user_id,
            MemoryDocumentVersion.revision == version_revision,
        )
    )
    if version is None:
        await db.rollback()
        raise MemoryDocumentNotFound("文档版本不存在")
    old_ai_enabled = row.ai_enabled
    row.title = version.title
    row.category = version.category
    row.content_markdown = version.content_markdown
    row.revision += 1
    row.updated_at = datetime.now(UTC)
    db.add(
        MemoryDocumentVersion(
            document_id=row.id,
            owner_user_id=owner_user_id,
            revision=row.revision,
            title=row.title,
            category=row.category,
            content_markdown=row.content_markdown,
            action="RESTORE",
        )
    )
    if old_ai_enabled:
        await _bump_context_revision(db, owner_user_id)
    await db.commit()
    await db.refresh(row)
    return await get_document(db, owner_user_id=owner_user_id, document_id=row.id) or _document_dto(
        row
    )


async def delete_document(
    db: AsyncSession, *, owner_user_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    row = await db.scalar(
        select(MemoryDocument)
        .where(MemoryDocument.id == document_id, MemoryDocument.owner_user_id == owner_user_id)
        .with_for_update()
    )
    if row is None:
        await db.rollback()
        raise MemoryDocumentNotFound("文档不存在")
    was_enabled = row.ai_enabled
    await db.delete(row)
    if was_enabled:
        await _bump_context_revision(db, owner_user_id)
    await db.commit()
