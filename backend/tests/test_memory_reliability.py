"""Account isolation, withdrawal, expiry and late-write regressions with synthetic students."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.jobs.memory_worker import run_once
from app.modules.ai.extraction import ExtractionFailure
from app.modules.memory.automatic import (
    KeywordMemoryRetriever,
    apply_extraction,
    enqueue_run,
    history_backfill,
    item_action,
    settings_update,
    state_for,
    utcnow,
)
from app.modules.memory.automatic_models import (
    ConversationMemorySummary,
    MemoryTask,
    PersonalMemoryItem,
    PersonalMemoryState,
)
from app.modules.memory.contracts import ExtractionResponse
from app.modules.memory.service import create_document, update_document
from app.modules.memory.summaries import recall_summary
from app.modules.teaching.models import ConversationMessage
from app.modules.teaching.service import create_free_session, create_turn
from tests.test_automatic_memory import response, saved_source, source, student


def with_summary(s, *, fact=True, text="希望讨论天文主题"):
    result = response(s) if fact else ExtractionResponse(request_id="test", facts=[])
    return result.model_copy(
        update={
            "summaries": ExtractionResponse.model_validate(
                {
                    "request_id": "test",
                    "facts": [],
                    "summaries": [
                        {
                            "session_id": s.session_id,
                            "summary": text,
                            "source_message_ids": [s.id],
                        }
                    ],
                }
            ).summaries
        }
    )


@pytest.mark.asyncio
async def test_unknown_cross_owner_assistant_and_tampered_sources_are_rejected(
    content_session,
    test_settings,
):
    db = content_session
    owner = await student(test_settings, "reliable.owner")
    other = await student(test_settings, "reliable.other")
    mine = await saved_source(db, owner)
    theirs = await saved_source(db, other)
    teacher = await saved_source(db, owner)
    await db.execute(
        update(ConversationMessage)
        .where(
            ConversationMessage.id == uuid.UUID(teacher.id),
        )
        .values(role="ASSISTANT")
    )
    for bad in [
        source(),
        theirs,
        teacher,
        mine.model_copy(update={"text": "我喜欢物理。"}),
        mine.model_copy(update={"session_id": theirs.session_id}),
        mine.model_copy(update={"observed_at": utcnow().isoformat()}),
    ]:
        assert await apply_extraction(db, owner.id, with_summary(bad), [bad]) == 0
    assert await db.scalar(select(PersonalMemoryItem)) is None
    assert await db.scalar(select(ConversationMemorySummary)) is None
    assert await apply_extraction(db, owner.id, response(mine), [mine]) == 1


@pytest.mark.asyncio
async def test_key_alias_deduplication_and_changed_retry_are_idempotent(
    content_session,
    test_settings,
):
    db = content_session
    owner = await student(test_settings)
    first = await saved_source(db, owner)
    await apply_extraction(db, owner.id, response(first), [first])
    assert await apply_extraction(db, owner.id, response(first, "喜欢物理"), [first]) == 0
    second = await saved_source(db, owner)
    await apply_extraction(
        db, owner.id, response(second, "喜欢天文。", key="interest:astronomy"), [second]
    )
    rows = list(await db.scalars(select(PersonalMemoryItem)))
    assert len(rows) == 1 and len(rows[0].sources) == 2
    assert rows[0].revision == 2


@pytest.mark.asyncio
async def test_conflicts_use_source_time_instead_of_response_order(content_session, test_settings):
    db = content_session
    owner = await student(test_settings)
    old = await saved_source(db, owner, "我喜欢物理。", observed_at=utcnow() - timedelta(days=1))
    new = await saved_source(db, owner)
    result = ExtractionResponse(
        request_id="test",
        facts=[
            response(new).facts[0],
            response(old, "喜欢物理").facts[0],
        ],
    )
    await apply_extraction(db, owner.id, result, [new, old])
    row = await db.scalar(select(PersonalMemoryItem))
    assert row.statement == "喜欢天文" and row.observed_at.isoformat() == new.observed_at


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["EDIT", "FORGET"])
async def test_new_key_category_and_paraphrase_cannot_reactivate_protected_facts(
    content_session,
    test_settings,
    action,
):
    db = content_session
    owner = await student(test_settings)
    s = await saved_source(db, owner)
    await apply_extraction(db, owner.id, with_summary(s), [s])
    await db.commit()
    item = await db.scalar(select(PersonalMemoryItem))
    await item_action(
        db,
        owner.id,
        item.id,
        base_revision=1,
        action=action,
        statement="现在更喜欢生物" if action == "EDIT" else None,
    )
    assert await apply_extraction(db, owner.id, response(s, key="different-key"), [s]) == 0
    fresh = await saved_source(db, owner, "我爱观测星空。")
    result = with_summary(fresh, text="喜欢观测星空")
    result.facts[0].key = "new-topic:stargazing"
    result.facts[0].category = "LEARNING"
    result.facts[0].statement = "爱好观测星空"
    await apply_extraction(db, owner.id, result, [fresh])
    await db.commit()
    alias = await db.scalar(
        select(PersonalMemoryItem).where(
            PersonalMemoryItem.key == "new-topic:stargazing",
        )
    )
    assert alias.status == "CANDIDATE"
    retry_source = await saved_source(db, owner, "我爱观测星空。")
    repeated = response(retry_source, "爱好观测星空", key="new-topic:stargazing")
    repeated.facts[0].category = "LEARNING"
    await apply_extraction(db, owner.id, repeated, [retry_source])
    assert alias.status == "CANDIDATE"
    recalled = await KeywordMemoryRetriever().retrieve(db, owner.id, "我的兴趣")
    assert all("星空" not in i["summary"] and "天文" not in i["summary"] for i in recalled)
    assert (
        await recall_summary(db, owner.id, s.session_id, await state_for(db, owner.id), utcnow())
        is None
    )
    # Only an explicit student decision makes the new wording usable.
    await item_action(db, owner.id, alias.id, base_revision=alias.revision, action="CONFIRM")
    assert any(
        "星空" in i["summary"]
        for i in await KeywordMemoryRetriever().retrieve(db, owner.id, "星空")
    )


@pytest.mark.asyncio
async def test_summary_replay_expiry_and_unproven_legacy_prose(content_session, test_settings):
    db = content_session
    owner = await student(test_settings)
    s = await saved_source(db, owner)
    result = with_summary(s)
    result.facts[0].valid_until = (utcnow() + timedelta(days=1)).isoformat()
    await apply_extraction(db, owner.id, result, [s])
    await db.commit()
    state = await state_for(db, owner.id)
    initial_revision = state.content_revision
    assert await recall_summary(db, owner.id, s.session_id, state, utcnow())
    await apply_extraction(db, owner.id, with_summary(s, text="模型重试的不同措辞"), [s])
    assert state.content_revision == initial_revision
    assert (
        await recall_summary(db, owner.id, s.session_id, state, utcnow() + timedelta(days=2))
        is None
    )
    row = await db.scalar(select(ConversationMemorySummary))
    row.content = "无法验证来源的旧摘要"
    await db.flush()
    assert await recall_summary(db, owner.id, s.session_id, state, utcnow()) is None


@pytest.mark.asyncio
async def test_recall_filters_before_ranking_and_obeys_count_length_and_owner(
    content_session,
    test_settings,
):
    db = content_session
    owner = await student(test_settings, "recall.owner")
    other = await student(test_settings, "recall.other")
    old = utcnow() - timedelta(days=30)
    relevant = PersonalMemoryItem(
        owner_user_id=owner.id,
        key="interest:天文",
        category="INTEREST",
        statement="喜欢天文",
        observed_at=old,
        updated_at=old,
        sources=[],
    )
    db.add(relevant)
    for n in range(510):
        db.add(
            PersonalMemoryItem(
                owner_user_id=owner.id,
                key=f"unrelated:{n}",
                category="INTEREST",
                statement="喜欢跑步",
                observed_at=utcnow(),
                sources=[],
                manual=True,
            )
        )
    for key, status, expires, user in [
        ("expired", "ACTIVE", old, owner),
        ("forgotten", "REMOVED", None, owner),
        ("candidate", "CANDIDATE", None, owner),
        ("other", "ACTIVE", None, other),
    ]:
        db.add(
            PersonalMemoryItem(
                owner_user_id=user.id,
                key=key,
                category="INTEREST",
                statement="天文",
                observed_at=utcnow(),
                valid_until=expires,
                status=status,
                sources=[],
            )
        )
    await db.commit()
    retriever = KeywordMemoryRetriever()
    results = await retriever.retrieve(db, owner.id, "天文")
    assert len(results) == 1 and str(relevant.id) in results[0]["id"]
    assert await retriever.retrieve(db, owner.id, "完全无关的关键词") == []
    results = await retriever.retrieve(db, owner.id, "我的兴趣", limit=999)
    assert len(results) == 6 and all(len(i["summary"]) <= 400 for i in results)
    assert await retriever.retrieve(db, owner.id, "我的兴趣", limit=-1) == []


async def queued_turn(db, settings, owner, text="我喜欢天文。"):
    session = await create_free_session(db, settings=settings, user=owner)
    run, _ = await create_turn(
        db,
        user=owner,
        session=session,
        operation="TEACH_TURN",
        message=text,
        idempotency_key=str(uuid.uuid4()),
    )
    run.status = "SUCCEEDED"
    await enqueue_run(db, run, immediate=True)
    await db.commit()
    return session, run


@pytest.mark.asyncio
@pytest.mark.parametrize("withdrawal", ["document", "cancel"])
async def test_late_worker_after_document_edit_or_all_task_cancel_has_no_write(
    content_session,
    test_settings,
    withdrawal,
):
    db = content_session
    owner = await student(test_settings)
    settings = test_settings.model_copy(update={"gateway_mode": "fixture"})
    document = await create_document(
        db,
        owner_user_id=owner.id,
        title="个人记忆.md",
        category="NOTE",
        content_markdown="我喜欢图解",
        is_primary=True,
    )
    await queued_turn(db, settings, owner)

    async def late(_settings, payload, _target):
        if withdrawal == "document":
            await update_document(
                db,
                owner_user_id=owner.id,
                document_id=uuid.UUID(document["id"]),
                base_revision=1,
                content_markdown="我希望先提示再解释",
            )
        else:
            await db.execute(update(MemoryTask).values(status="CANCELLED", reason="USER_CANCELLED"))
            await db.commit()
        return with_summary(payload.sources[0])

    await run_once(settings, extractor=late)
    tasks = list(await db.scalars(select(MemoryTask).execution_options(populate_existing=True)))
    assert tasks and all(task.status == "CANCELLED" for task in tasks)
    assert await db.scalar(select(PersonalMemoryItem)) is None
    assert await db.scalar(select(ConversationMemorySummary)) is None


@pytest.mark.asyncio
async def test_collection_and_use_switches_are_independent(content_session, test_settings):
    db = content_session
    owner = await student(test_settings)
    s = await saved_source(db, owner)
    await apply_extraction(db, owner.id, response(s), [s])
    await db.commit()
    settings = test_settings.model_copy(update={"gateway_mode": "fixture"})
    cancelled_session, _ = await queued_turn(db, settings, owner)
    await settings_update(db, owner.id, 1, False, True)
    assert await KeywordMemoryRetriever().retrieve(db, owner.id, "天文")
    assert await run_once(settings) == 0
    assert await apply_extraction(db, owner.id, response(s), [s]) == 0
    await settings_update(db, owner.id, 2, True, False)
    backfill = await history_backfill(db, owner.id, [cancelled_session.id])
    assert backfill["accepted_runs"] == 1
    assert await run_once(settings) == 1
    await queued_turn(db, settings, owner, "我喜欢足球。")
    assert await run_once(settings) == 1
    assert len(list(await db.scalars(select(PersonalMemoryItem)))) == 2
    assert await KeywordMemoryRetriever().retrieve(db, owner.id, "我的兴趣") == []


@pytest.mark.asyncio
async def test_partial_task_cancel_filters_facts_and_summary_sources(
    content_session, test_settings
):
    db = content_session
    owner = await student(test_settings)
    settings = test_settings.model_copy(update={"gateway_mode": "fixture"})
    _, first = await queued_turn(db, settings, owner)
    _, second = await queued_turn(db, settings, owner, "我喜欢足球。")

    async def partially_cancelled(_settings, payload, _target):
        await db.execute(
            update(MemoryTask)
            .where(MemoryTask.source_run_id == str(second.id))
            .values(status="CANCELLED", reason="USER_CANCELLED")
        )
        await db.commit()
        facts = [
            response(
                s,
                "喜欢天文" if "天文" in s.text else "喜欢足球",
                key="interest:天文" if "天文" in s.text else "interest:足球",
            ).facts[0]
            for s in payload.sources
        ]
        summaries = [with_summary(s).summaries[0] for s in payload.sources]
        return ExtractionResponse(request_id=payload.request_id, facts=facts, summaries=summaries)

    assert await run_once(settings, extractor=partially_cancelled) == 2
    items = list(await db.scalars(select(PersonalMemoryItem)))
    assert len(items) == 1 and items[0].statement == "喜欢天文"
    tasks = list(await db.scalars(select(MemoryTask).execution_options(populate_existing=True)))
    assert {t.source_run_id: t.status for t in tasks} == {
        str(first.id): "SUCCEEDED",
        str(second.id): "CANCELLED",
    }


@pytest.mark.asyncio
async def test_timeout_has_no_automatic_retry_and_logs_no_exception_body(
    content_session,
    test_settings,
    caplog,
):
    db = content_session
    owner = await student(test_settings)
    settings = test_settings.model_copy(update={"gateway_mode": "fixture"})
    await queued_turn(db, settings, owner)

    async def fails(*_args):
        raise RuntimeError("synthetic-secret-and-personal-text")

    await run_once(settings, extractor=fails)
    task = await db.scalar(select(MemoryTask).execution_options(populate_existing=True))
    assert task.status == "RETRY_REQUIRED" and "synthetic-secret" not in caplog.text
    assert await run_once(settings, extractor=fails) == 0


@pytest.mark.asyncio
async def test_result_arriving_after_lease_expiry_waits_for_explicit_retry(
    content_session,
    test_settings,
):
    db = content_session
    owner = await student(test_settings)
    settings = test_settings.model_copy(update={"gateway_mode": "fixture"})
    await queued_turn(db, settings, owner)

    async def expired(_settings, payload, _target):
        await db.execute(
            update(PersonalMemoryState).values(
                lease_until=utcnow() - timedelta(seconds=1),
            )
        )
        await db.commit()
        return with_summary(payload.sources[0])

    await run_once(settings, extractor=expired)
    task = await db.scalar(select(MemoryTask).execution_options(populate_existing=True))
    assert task.status == "RETRY_REQUIRED" and task.reason == "INTERRUPTED_UNCERTAIN"
    assert await db.scalar(select(PersonalMemoryItem)) is None


@pytest.mark.asyncio
async def test_retry_and_expired_lease_recovery_do_not_duplicate_memory(
    content_session, test_settings
):
    db = content_session
    settings = test_settings.model_copy(
        update={"gateway_mode": "fixture", "memory_coalesce_seconds": 0}
    )
    owner = await student(test_settings)
    await queued_turn(db, settings, owner)

    async def rate_limit(*_args):
        raise ExtractionFailure("UPSTREAM_RATE_LIMITED", retryable=True)

    assert await run_once(settings, extractor=rate_limit) == 1
    task = await db.scalar(select(MemoryTask).execution_options(populate_existing=True))
    assert task.status == "QUEUED" and task.attempt == 1 and task.available_at > utcnow()
    task.available_at = utcnow() - timedelta(seconds=1)
    await db.commit()
    assert await run_once(settings) == 1
    task = await db.scalar(select(MemoryTask).execution_options(populate_existing=True))
    assert task.status == "SUCCEEDED" and task.attempt == 2
    token = uuid.uuid4()
    state = await state_for(db, owner.id)
    state.lease_token, state.lease_until = token, utcnow() - timedelta(seconds=1)
    task.status, task.lease_token = "RUNNING", token
    await db.commit()
    assert await run_once(settings) == 0
    task = await db.scalar(select(MemoryTask).execution_options(populate_existing=True))
    assert task.status == "RETRY_REQUIRED" and task.reason == "INTERRUPTED_UNCERTAIN"
    assert len(list(await db.scalars(select(PersonalMemoryItem)))) == 1
