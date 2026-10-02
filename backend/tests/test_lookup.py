"""Read-only tool boundaries, owner filtering and durable teaching lookup rounds."""

import copy
import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.integrations.knodo.types import GatewayStatus
from app.jobs.teaching_worker import execute_run, session_factory
from app.modules.ai.service import execute_backend_capability
from app.modules.assessment.models import QuizAttempt, QuizQuestion, QuizSession
from app.modules.content.models import ChapterReviewState, ReadingEvent
from app.modules.lookup.rounds import planning_context
from app.modules.lookup.schemas import LookupInput, LookupPlan, LookupQuery
from app.modules.lookup.service import LookupRuntime, course_search, date_bounds, learning_progress
from app.modules.lookup.targets import resolve_target
from app.modules.resources.models import Resource
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    prepare_fixture_course,
    teaching_settings,
)

PASSWORD = "synthetic-lookup-pass"


async def student(settings, name="lookup.owner", stage="JUNIOR", grade=8):
    return await create_synthetic_user(
        settings, username=name, password=PASSWORD, stage=stage, grade=grade
    )


async def quiz(db, owner, *, incorrect=True, answered=True, title="已提交练习"):
    row = QuizSession(
        owner_user_id=owner.id,
        source_conversation_id=uuid.uuid4(),
        source_title=title,
        curriculum_revision="lookup-fixture",
        stage="JUNIOR",
        grade=8,
        source_kind="AI_DRAFT",
        source_label="fixture",
        difficulty="EASY",
        question_count=2,
        max_attempts=3,
        max_hints=2,
        scoring_version="v1",
        thresholds_version="v1",
    )
    db.add(row)
    await db.flush()
    questions = []
    for index in range(2):
        q = QuizQuestion(
            session_id=row.id,
            position=index,
            question_key=f"Q{index}",
            objective_id="lookup",
            type="TRUE_FALSE",
            stem=f"{title}问题{index}",
            correct_answer=True,
            explanation=f"{title}已释放解析{index}",
            hints=["尚未释放提示"],
            source_refs=[],
            origin="FIXTURE",
        )
        db.add(q)
        questions.append(q)
    await db.flush()
    if answered:
        db.add(
            QuizAttempt(
                owner_user_id=owner.id,
                session_id=row.id,
                question_id=questions[0].id,
                attempt_no=1,
                answer=not incorrect,
                outcome="INCORRECT" if incorrect else "CORRECT",
                is_correct=not incorrect,
                idempotency_key=str(uuid.uuid4()),
                payload_hash="a" * 64,
                scoring_version="v1",
            )
        )
    await db.commit()
    return row, questions


@pytest.mark.parametrize(
    "payload",
    [
        {"owner_user_id": str(uuid.uuid4())},
        {"limit": 11},
        {"limit": 0},
        {"limit": True},
        {"limit": "5"},
        {"keyword": "x" * 121},
        {"topic": "x" * 81},
        {"since": "2026-99-02"},
        {"until": "2026-1-2"},
        {"url": "https://evil.test"},
        {"question_id": str(uuid.uuid4())},
        {"db": "DROP TABLE"},
        {"python_path": "os.system"},
    ],
)
def test_strict_parameters(payload):
    with pytest.raises(ValidationError):
        LookupInput.model_validate(payload)


def test_plan_limits_and_filters():
    plan = {
        "schema_version": "k12.teaching.turn.v1",
        "kind": "lookup_request",
        "request_id": "r",
        "lesson_session_id": "s",
        "base_revision": 0,
        "queries": [{"tool": "COURSE_SEARCH", "parameters": {}}],
    }
    assert LookupPlan.model_validate(plan).queries[0].parameters.limit == 5
    for queries in ([{"tool": "DELETE_GRADES"}], plan["queries"] * 2, plan["queries"] * 4):
        with pytest.raises(ValidationError):
            LookupPlan.model_validate({**plan, "queries": queries})
    with pytest.raises(ValidationError):
        LookupQuery(tool="WRONG_QUESTIONS", parameters={"content_type": "CODE"})
    with pytest.raises(ValidationError):
        LookupQuery(tool="COURSE_SEARCH", parameters={"since": "今天"})


def test_relative_dates_use_shanghai_and_inclusive_day():
    start, end = date_bounds(
        LookupInput(since="昨天", until="昨天"), datetime(2026, 10, 2, 17, tzinfo=UTC)
    )
    assert start.isoformat() == "2026-10-02T00:00:00+08:00"
    assert end.isoformat() == "2026-10-03T00:00:00+08:00"
    with pytest.raises(ValueError):
        date_bounds(LookupInput(since="2026-10-03", until="2026-10-01"), datetime.now(UTC))


@pytest.mark.asyncio
async def test_owner_wrong_records_and_unsubmitted_answers(content_session, test_settings):
    db, settings = content_session, teaching_settings(test_settings)
    owner, other = await student(settings), await student(settings, "lookup.other")
    own_quiz, own_questions = await quiz(db, owner)
    await quiz(db, other, title="other-secret")
    await quiz(db, owner, answered=False, title="unsubmitted-secret")
    runtime = LookupRuntime(db, owner.id, "JUNIOR", settings)
    result = await execute_backend_capability(db, "WRONG_QUESTIONS", {}, {}, runtime=runtime)
    serialized = result.model_dump_json()
    assert result.total == 1
    assert str(own_questions[0].id) in serialized
    assert own_questions[0].explanation in serialized
    assert "other-secret" not in serialized and "unsubmitted-secret" not in serialized
    assert "correct_answer" not in serialized and "尚未释放提示" not in serialized
    assert str(own_questions[1].id) not in serialized
    malicious = await execute_backend_capability(
        db, "WRONG_QUESTIONS", {"keyword": "%' OR 1=1 --"}, {}, runtime=runtime
    )
    assert malicious.status == "EMPTY"
    with pytest.raises(ValidationError):
        await execute_backend_capability(
            db, "WRONG_QUESTIONS", {"owner_user_id": str(other.id)}, {}, runtime=runtime
        )
    with pytest.raises(ValueError):
        await execute_backend_capability(db, "DELETE_RECORDS", {}, {}, runtime=runtime)
    progress = await learning_progress(LookupInput(content_type="QUIZ"), {}, runtime=runtime)
    assert "other-secret" not in progress.model_dump_json()
    own_card = next(c for c in progress.cards if c.target.id == str(own_quiz.id))
    assert "已答 1/2" in own_card.description
    assert "掌握" not in own_card.description
    assert (
        await resolve_target(LookupRuntime(db, other.id, "JUNIOR", settings), own_card.target)
        is None
    )


@pytest.mark.asyncio
async def test_course_visibility_search_and_withdrawal(content_session, test_settings):
    db, settings = content_session, teaching_settings(test_settings)
    owner = await student(settings, stage="PRIMARY_LOWER", grade=2)
    revision = await prepare_fixture_course(db)
    runtime = LookupRuntime(db, owner.id, "PRIMARY_LOWER", settings)
    result = await course_search(LookupInput(), {}, runtime=runtime)
    assert result.status == "OK"
    assert all(c.target.type == "CHAPTER" for c in result.cards)
    card = next(c for c in result.cards if c.target.id == str(revision.chapter_id))
    assert await resolve_target(runtime, card.target) == card.route
    for stage, grade in [("PRIMARY_UPPER", 5), ("JUNIOR", 8), ("SENIOR", 11)]:
        user = await student(settings, f"lookup.{stage}", stage, grade)
        other = await course_search(
            LookupInput(), {}, runtime=LookupRuntime(db, user.id, stage, settings)
        )
        assert all(c.target.id != str(revision.chapter_id) for c in other.cards)
    empty = await course_search(LookupInput(keyword="%' OR 1=1 --"), {}, runtime=runtime)
    assert empty.status == "EMPTY"
    state = await db.get(ChapterReviewState, revision.id)
    state.publication_status = "WITHDRAWN"
    state.withdrawn_by = "lookup-test"
    state.withdrawn_at = datetime.now(UTC)
    await db.commit()
    assert await resolve_target(runtime, card.target) is None
    assert all(
        c.target.id != str(revision.chapter_id)
        for c in (await course_search(LookupInput(), {}, runtime=runtime)).cards
    )


@pytest.mark.asyncio
async def test_resource_visibility_and_missing_files(content_session, test_settings):
    db, settings = content_session, teaching_settings(test_settings)
    owner = await student(settings)
    for index, (stage, fixture, status) in enumerate(
        [
            ("JUNIOR", True, "DRAFT"),
            ("SENIOR", True, "DRAFT"),
            ("JUNIOR", False, "DRAFT"),
            ("JUNIOR", True, "WITHDRAWN"),
        ]
    ):
        db.add(
            Resource(
                stable_slug=f"lookup-resource-{index}",
                title=f"resource-{index}",
                description="安全资料",
                kind="PDF",
                stage=stage,
                source_kind="SYNTHETIC_FIXTURE" if fixture else "NEW_SOURCE",
                license_code="SYNTHETIC-FIXTURE" if fixture else "PROJECT-ORIGINAL",
                is_test_fixture=fixture,
                publication_status=status,
                uploaded_by_user_id=owner.id,
            )
        )
    await db.commit()
    runtime = LookupRuntime(db, owner.id, "JUNIOR", settings)
    result = await course_search(LookupInput(content_type="RESOURCE"), {}, runtime=runtime)
    assert result.total == 1 and result.cards[0].title == "resource-0"
    assert result.cards[0].status == "UNAVAILABLE" and result.cards[0].target is None


@pytest.mark.asyncio
async def test_queries_do_not_write_and_limit_and_reading_semantics(content_session, test_settings):
    db, settings = content_session, teaching_settings(test_settings)
    user = await student(settings, stage="PRIMARY_LOWER", grade=2)
    revision = await prepare_fixture_course(db)
    db.add(
        ReadingEvent(
            user_id=user.id,
            chapter_id=revision.chapter_id,
            revision_id=revision.id,
            client_event_id="lookup-reading-1",
            event_kind="ENTER",
        )
    )
    await db.commit()
    for index in range(7):
        await quiz(db, user, title=f"练习{index}")
    # Quiz stage must match the selected viewer, so these seven JUNIOR records stay hidden.
    runtime = LookupRuntime(db, user.id, "PRIMARY_LOWER", settings)
    before = await db.scalar(select(func.count()).select_from(ReadingEvent))
    async with session_factory(settings)() as readonly:
        await readonly.execute(text("SET TRANSACTION READ ONLY"))
        result = await execute_backend_capability(
            readonly,
            "LEARNING_PROGRESS",
            {},
            {},
            runtime=LookupRuntime(readonly, user.id, "PRIMARY_LOWER", settings),
        )
    assert result.total == 1
    assert "不代表读完或掌握" in result.cards[0].description
    assert before == await db.scalar(select(func.count()).select_from(ReadingEvent))
    assert await resolve_target(runtime, result.cards[0].target)


@pytest.mark.asyncio
async def test_reading_date_window_precedes_per_chapter_aggregation(content_session, test_settings):
    db, settings = content_session, teaching_settings(test_settings)
    owner = await student(settings, stage="PRIMARY_LOWER", grade=2)
    revision = await prepare_fixture_course(db)
    earlier = datetime(2026, 9, 30, 4, tzinfo=UTC)
    later = datetime(2026, 10, 1, 4, tzinfo=UTC)
    for index, moment in enumerate((earlier, later)):
        db.add(
            ReadingEvent(
                user_id=owner.id,
                chapter_id=revision.chapter_id,
                revision_id=revision.id,
                client_event_id=f"lookup-reading-day-{index}",
                event_kind="BLOCK_VIEW",
                block_id="b3",
                created_at=moment,
            )
        )
    await db.commit()
    runtime = LookupRuntime(db, owner.id, "PRIMARY_LOWER", settings)
    yesterday = await learning_progress(
        LookupInput(content_type="READING", since="2026-09-30", until="2026-09-30"),
        {},
        runtime=runtime,
    )
    assert yesterday.total == 1
    assert yesterday.cards[0].target.id == str(revision.chapter_id)
    assert yesterday.cards[0].recorded_at == earlier.isoformat()
    today = await learning_progress(
        LookupInput(content_type="READING", since="2026-10-01", until="2026-10-01"),
        {},
        runtime=runtime,
    )
    assert today.total == 1 and today.cards[0].recorded_at == later.isoformat()
    all_days = await learning_progress(LookupInput(content_type="READING"), {}, runtime=runtime)
    assert all_days.total == 1 and all_days.cards[0].recorded_at == later.isoformat()


@pytest.mark.asyncio
async def test_old_quiz_later_attempts_use_event_dates_and_window_counts(
    content_session, test_settings
):
    db, settings = content_session, teaching_settings(test_settings)
    owner = await student(settings)
    activity, questions = await quiz(db, owner, answered=False, title="跨天作答练习")
    activity.created_at = datetime(2026, 9, 28, 4, tzinfo=UTC)
    earlier = datetime(2026, 9, 30, 4, tzinfo=UTC)
    later = datetime(2026, 10, 1, 4, tzinfo=UTC)
    for question, attempt_no, correct, moment in (
        (questions[0], 1, False, earlier),
        (questions[0], 2, True, later),
        (questions[1], 1, True, later),
    ):
        db.add(
            QuizAttempt(
                owner_user_id=owner.id,
                session_id=activity.id,
                question_id=question.id,
                attempt_no=attempt_no,
                answer=correct,
                outcome="CORRECT" if correct else "INCORRECT",
                is_correct=correct,
                idempotency_key=str(uuid.uuid4()),
                payload_hash="a" * 64,
                scoring_version="v1",
                created_at=moment,
            )
        )
    activity.status, activity.completed_at = "COMPLETED", later
    await db.commit()
    untouched, _ = await quiz(db, owner, answered=False, title="仅生成而未作答的练习")
    untouched.created_at = earlier
    await db.commit()
    runtime = LookupRuntime(db, owner.id, "JUNIOR", settings)
    yesterday = await learning_progress(
        LookupInput(content_type="QUIZ", since="2026-09-30", until="2026-09-30"),
        {},
        runtime=runtime,
    )
    assert yesterday.total == 1 and yesterday.cards[0].target.id == str(activity.id)
    assert yesterday.cards[0].recorded_at == earlier.isoformat()
    assert "查询时间内：作答 1 次，涉及 1/2 题，最近作答答对 0 题" in yesterday.cards[0].description
    assert "当前练习已完成" in yesterday.cards[0].description
    assert "查询时间内完成" not in yesterday.cards[0].description
    today = await learning_progress(
        LookupInput(content_type="QUIZ", since="2026-10-01", until="2026-10-01"),
        {},
        runtime=runtime,
    )
    assert today.total == 1 and today.cards[0].recorded_at == later.isoformat()
    assert "查询时间内：作答 2 次，涉及 2/2 题，最近作答答对 2 题" in today.cards[0].description
    assert "练习在查询时间内完成" in today.cards[0].description
    creation_day = await learning_progress(
        LookupInput(content_type="QUIZ", since="2026-09-28", until="2026-09-28"),
        {},
        runtime=runtime,
    )
    assert creation_day.status == "EMPTY"
    all_days = await learning_progress(LookupInput(content_type="QUIZ"), {}, runtime=runtime)
    assert all_days.total == 1
    assert "已答 2/2 题，最近作答答对 2 题" in all_days.cards[0].description


@pytest.mark.asyncio
async def test_quiz_completion_is_a_date_scoped_learning_event(content_session, test_settings):
    db, settings = content_session, teaching_settings(test_settings)
    owner = await student(settings)
    activity, _ = await quiz(db, owner, answered=False, title="已有完成回执的练习")
    activity.created_at = datetime(2026, 9, 28, 4, tzinfo=UTC)
    activity.status = "COMPLETED"
    activity.completed_at = datetime(2026, 9, 30, 4, tzinfo=UTC)
    await db.commit()
    result = await learning_progress(
        LookupInput(content_type="QUIZ", since="2026-09-30", until="2026-09-30"),
        {},
        runtime=LookupRuntime(db, owner.id, "JUNIOR", settings),
    )
    assert result.total == 1 and result.cards[0].target.id == str(activity.id)
    assert result.cards[0].recorded_at == activity.completed_at.isoformat()
    assert "查询时间内：作答 0 次" in result.cards[0].description
    assert "练习在查询时间内完成" in result.cards[0].description


async def turn(settings, client, message, key):
    created = await client.post(
        "/api/v1/conversations", json={}, headers=await csrf_headers(client)
    )
    session_id = created.json()["id"]
    sent = await client.post(
        f"/api/v1/conversations/{session_id}/messages",
        json={
            "message": message,
            "idempotency_key": key,
            "scene": {"page_type": "conversation", "route": "/conversations"},
        },
        headers=await csrf_headers(client),
    )
    assert sent.status_code == 202, sent.text
    return session_id, sent.json()["run"]["id"]


@pytest.mark.asyncio
async def test_mixed_round_final_cards_history_and_duplicate_receipt(
    content_session, test_settings
):
    settings = teaching_settings(test_settings)
    await student(settings)
    client = create_app_client(settings)
    async with client:
        await login(client, "lookup.owner", PASSWORD)
        session_id, run_id = await turn(
            settings, client, "查课程、本人错题和学习进度", "mixed-lookup"
        )
        gateway = client._transport.app.state.gateway
        original = gateway.invoke
        requests = []

        async def observe(operation, payload, **kwargs):
            requests.append(copy.deepcopy(payload))
            snapshot = (await client.get(f"/api/v1/agent-runs/{run_id}")).json()
            assert snapshot["draft_markdown"] is None
            return await original(operation, payload, **kwargs)

        gateway.invoke = observe
        assert await execute_run(settings, gateway, run_id) == "SUCCEEDED"
        assert len(requests) == 2
        assert requests[0]["lookup_context"]["phase"] == "PLAN"
        second = requests[1]
        assert second["lookup_context"]["phase"] == "FINAL"
        assert len(second["lookup_context"]["results"]) == 3
        assert not second.get("personal_context")
        assert "results" not in second["student_input"]
        history = (await client.get(f"/api/v1/conversations/{session_id}")).json()
        assert len(history["messages"]) == 2
        cards = history["messages"][-1]["card"]["lookup_cards"]
        assert {c["status"] for c in cards} == {"EMPTY"}
        assert "lookup_request" not in history["messages"][-1]["content_markdown"]
        assert await execute_run(settings, gateway, run_id) == "LEASE_HELD"
        assert len(requests) == 2
        assert (await client.get(f"/api/v1/conversations/{session_id}")).json()["messages"][-1][
            "card"
        ]["lookup_cards"] == cards


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "behavior", ["again", "forged", "failed", "cancel", "cancel_second", "normal"]
)
async def test_round_rejects_recursion_forged_facts_and_preserves_cancel(
    content_session, test_settings, behavior
):
    settings = teaching_settings(test_settings)
    await student(settings)
    client = create_app_client(settings)
    async with client:
        await login(client, "lookup.owner", PASSWORD)
        sid, rid = await turn(
            settings,
            client,
            "你好" if behavior == "normal" else "查询本人错题",
            f"lookup-{behavior}",
        )
        gateway = client._transport.app.state.gateway
        original = gateway.invoke
        calls = []

        async def intercept(operation, payload, **kwargs):
            result = await original(operation, payload, **kwargs)
            calls.append(copy.deepcopy(payload))
            if len(calls) == 1 and behavior == "cancel":
                await client.post(
                    f"/api/v1/agent-runs/{rid}/cancel", headers=await csrf_headers(client)
                )
            if len(calls) == 2:
                if behavior == "cancel_second":
                    await client.post(
                        f"/api/v1/agent-runs/{rid}/cancel", headers=await csrf_headers(client)
                    )
                if behavior == "again":
                    return result.model_copy(update={"output": {"kind": "lookup_request"}})
                if behavior == "forged":
                    output = {
                        **result.output,
                        "message_markdown": "你已掌握100%，打开[成绩](https://evil.test)",
                    }
                    return result.model_copy(update={"output": output})
                if behavior == "failed":
                    return result.model_copy(
                        update={"status": GatewayStatus.FAILED, "output": None}
                    )
            return result

        gateway.invoke = intercept
        assert await execute_run(settings, gateway, rid) == (
            "CANCELLED" if behavior in ("cancel", "cancel_second") else "SUCCEEDED"
        )
        history = (await client.get(f"/api/v1/conversations/{sid}")).json()
        assert len(calls) == (1 if behavior in ("normal", "cancel") else 2)
        if behavior in ("cancel", "cancel_second"):
            assert len(history["messages"]) == 1
        else:
            final = history["messages"][-1]
            assert (
                "evil.test" not in final["content_markdown"]
                and "100%" not in final["content_markdown"]
            )
            if behavior == "again":
                assert "已被拒绝" in final["content_markdown"]
            if behavior == "normal":
                assert final["card"].get("lookup_cards", []) == []


def test_query_not_accepted_for_code_feedback():
    payload = {
        "schema_version": "k12.teaching.turn.v1",
        "kind": "lookup_request",
        "request_id": "r",
        "lesson_session_id": "s",
        "base_revision": 0,
        "queries": [{"tool": "WRONG_QUESTIONS", "parameters": {}}],
    }
    assert not default_registry().validate_response(Operation.TEACH_TURN, payload)
    assert default_registry().validate_response(Operation.CODE_FEEDBACK, payload)
    assert planning_context()["max_queries"] == 3


@pytest.mark.asyncio
async def test_populated_lookup_cards_are_local_and_bounded(content_session, test_settings):
    settings = teaching_settings(test_settings)
    owner = await student(settings)
    for index in range(12):
        await quiz(content_session, owner, title=f"本人练习{index}")
    async with session_factory(settings)() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        result = await execute_backend_capability(
            db,
            "WRONG_QUESTIONS",
            {"limit": 10},
            {},
            runtime=LookupRuntime(db, owner.id, "JUNIOR", settings),
        )
    assert len(result.cards) == 10 and result.total == 12 and result.truncated
    client = create_app_client(settings)
    async with client:
        await login(client, "lookup.owner", PASSWORD)
        sid, rid = await turn(settings, client, "查询本人错题", "populated-lookups")
        gateway = client._transport.app.state.gateway
        assert await execute_run(settings, gateway, rid) == "SUCCEEDED"
        history = (await client.get(f"/api/v1/conversations/{sid}")).json()
        card = history["messages"][-1]["card"]
        assert len(card["lookup_cards"]) == 6
        assert len(card["source_refs"]) == 5
        assert all(ref["source_id"].startswith("lookup:wrong:") for ref in card["source_refs"])
        target = next(item["target"] for item in card["lookup_cards"] if item["target"])
        response = await client.get(
            "/api/v1/learning/lookup-target", params={k: v for k, v in target.items() if v}
        )
        assert response.status_code == 200 and response.json()["route"].startswith(
            "/practice/sessions/"
        )
        other = await student(settings, "lookup.target.other")
        await login(client, "lookup.target.other", PASSWORD)
        assert (
            await client.get(
                "/api/v1/learning/lookup-target", params={k: v for k, v in target.items() if v}
            )
        ).status_code == 404
        assert other.id != owner.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [RuntimeError("synthetic backend failure"), ValueError("scope changed")]
)
async def test_lookup_failure_is_not_empty_and_does_not_become_student_memory(
    content_session,
    test_settings,
    monkeypatch,
    failure,
):
    from app.modules.lookup import rounds

    settings = teaching_settings(test_settings)
    await student(settings)

    async def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(rounds, "execute_backend_capability", fail)
    client = create_app_client(settings)
    async with client:
        await login(client, "lookup.owner", PASSWORD)
        sid, rid = await turn(settings, client, "查错题", "lookup-failure")
        gateway = client._transport.app.state.gateway
        original = gateway.invoke
        captured = []

        async def observe(operation, payload, **kwargs):
            captured.append(copy.deepcopy(payload))
            return await original(operation, payload, **kwargs)

        gateway.invoke = observe
        assert await execute_run(settings, gateway, rid) == "SUCCEEDED"
        history = (await client.get(f"/api/v1/conversations/{sid}")).json()
        expected = "FAILED" if isinstance(failure, RuntimeError) else "UNAVAILABLE"
        assert history["messages"][-1]["card"]["lookup_cards"][0]["status"] == expected
        assert captured[1]["lookup_context"]["results"][0]["status"] == expected
        assert captured[1]["student_input"] == captured[0]["student_input"]
        assert history["messages"][0]["content_markdown"] == "查错题"
        assert "synthetic backend failure" not in json.dumps(history)


@pytest.mark.asyncio
async def test_progress_code_and_watching_do_not_leak_hidden_payloads(
    content_session, test_settings
):
    from app.modules.codelab.models import CodeRun, CodeTaskRevision
    from app.modules.interactive.models import InteractiveRevision, InteractiveSession
    from app.modules.resources.service import store_for

    db, settings = content_session, teaching_settings(test_settings)
    owner = await student(settings)
    task = CodeTaskRevision(
        task_id="lookup-code",
        revision=1,
        status="DRAFT",
        title="编程记录",
        description="仅元数据",
        starter_code="",
        entrypoint="solve",
        io_contract={},
        examples=[],
        test_manifest={"secret": "hidden_test_private"},
        rubric={},
        chapter_binding={"stage": "JUNIOR"},
        source={},
        definition_sha256="a" * 64,
    )
    db.add(task)
    resource = Resource(
        stable_slug="lookup-lesson",
        title="讲解记录",
        description="安全的讲解",
        kind="INTERACTIVE",
        interactive_purpose="LESSON",
        interactive_subject="AI",
        stage="JUNIOR",
        source_kind="SYNTHETIC_FIXTURE",
        license_code="SYNTHETIC-FIXTURE",
        is_test_fixture=True,
        uploaded_by_user_id=owner.id,
    )
    db.add(resource)
    await db.flush()
    revision = InteractiveRevision(
        resource_id=resource.id,
        revision=1,
        package_storage_key="lookup/package.zip",
        package_sha256="a" * 64,
        document_storage_key="lookup/document.html",
        manifest={},
        capabilities=[],
        created_by_user_id=owner.id,
    )
    db.add(revision)
    await db.flush()
    resource.active_interactive_revision_id = revision.id
    # An activity completion on the baseline must never manufacture a viewed_at record.
    db.add(
        InteractiveSession(
            owner_user_id=owner.id,
            resource_id=resource.id,
            revision_id=revision.id,
            stage="JUNIOR",
            status="COMPLETED",
            completed_at=datetime.now(UTC),
            game_state={"private": "DO NOT EXTRACT ME"},
        )
    )
    db.add(
        CodeRun(
            owner_user_id=owner.id,
            task_id=task.task_id,
            task_revision=1,
            idempotency_key="lookup-code-run",
            code="private_source_code",
            code_sha256="b" * 64,
            status="SUCCEEDED",
            execution_status="SUCCEEDED",
            correctness_status="PARTIAL",
            deterministic_score=50,
            result={"hidden_tests": "DO NOT EXTRACT ME"},
            feedback={"reference_solution": "DO NOT EXTRACT ME"},
        )
    )
    db.add(
        CodeRun(
            owner_user_id=owner.id,
            task_id=task.task_id,
            task_revision=1,
            purpose="EXAMPLE",
            idempotency_key="lookup-example-run",
            code="example",
            code_sha256="c" * 64,
            status="SUCCEEDED",
            execution_status="SUCCEEDED",
            correctness_status="PASSED",
            deterministic_score=100,
        )
    )
    await db.commit()
    store = store_for(settings)
    path = store.root / "lookup/document.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<p>synthetic</p>")
    runtime = LookupRuntime(db, owner.id, "JUNIOR", settings)
    result = await learning_progress(LookupInput(), {}, runtime=runtime)
    assert len(result.cards) == 3
    dumped = result.model_dump_json()
    assert "DO NOT EXTRACT ME" not in dumped and "private_source_code" not in dumped
    assert "hidden_test" not in dumped and "reference_solution" not in dumped
    assert "尚无独立看完记录" in dumped and "成绩：50" in dumped
    assert "示例运行不计成绩" in dumped
    example_card = next(card for card in result.cards if "示例运行" in card.description)
    assert "100" not in example_card.description
    assert all([await resolve_target(runtime, c.target) for c in result.cards])
    # After A6 is integrated, a real viewing field is the only positive signal.
    viewing = await db.scalar(
        select(InteractiveSession).where(
            InteractiveSession.owner_user_id == owner.id,
            InteractiveSession.resource_id == resource.id,
        )
    )
    viewing.status = "ACTIVE"
    viewing.viewed_at = datetime.now(UTC)
    await db.commit()
    watched = await learning_progress(LookupInput(content_type="WATCHING"), {}, runtime=runtime)
    assert watched.total == 1
    assert "已看完（播放器报告，不代表掌握）" in watched.cards[0].description
    assert "成绩" not in watched.cards[0].description and viewing.status == "ACTIVE"
    assert "DO NOT EXTRACT ME" not in watched.model_dump_json()
    path.unlink()


@pytest.mark.asyncio
async def test_picturebook_progress_remains_owner_scoped(content_session, test_settings):
    from app.modules.learning.models import PicturebookProgress

    settings = teaching_settings(test_settings)
    owner = await student(settings, "lookup.picture.owner", "PRIMARY_LOWER", 2)
    other = await student(settings, "lookup.picture.other", "PRIMARY_LOWER", 2)
    content_session.add(PicturebookProgress(owner_user_id=owner.id, story_id="crow", page_index=1))
    content_session.add(
        PicturebookProgress(owner_user_id=other.id, story_id="tortoise", page_index=2)
    )
    await content_session.commit()
    runtime = LookupRuntime(content_session, owner.id, "PRIMARY_LOWER", settings)
    result = await learning_progress(LookupInput(content_type="READING"), {}, runtime=runtime)
    assert result.total == 1
    assert result.cards[0].target.id == "crow"
    assert "第 2 页" in result.cards[0].description
    assert await resolve_target(runtime, result.cards[0].target) == "/picturebooks/crow"
    assert (
        await resolve_target(
            LookupRuntime(content_session, other.id, "PRIMARY_LOWER", settings),
            result.cards[0].target,
        )
        is None
    )


@pytest.mark.asyncio
async def test_classroom_progress_and_knowledge_point_search(content_session, test_settings):
    from app.modules.content.models import KnowledgePoint, RevisionKnowledgePoint
    from app.modules.teaching.service import create_session

    db, settings = content_session, teaching_settings(test_settings)
    owner = await student(settings, "lookup.class.owner", "PRIMARY_LOWER", 2)
    other = await student(settings, "lookup.class.other", "PRIMARY_LOWER", 2)
    revision = await prepare_fixture_course(db)
    own = await create_session(db, settings=settings, user=owner, chapter_id=revision.chapter_id)
    peer = await create_session(db, settings=settings, user=other, chapter_id=revision.chapter_id)
    runtime = LookupRuntime(db, owner.id, "PRIMARY_LOWER", settings)
    active = await learning_progress(LookupInput(content_type="LESSON"), {}, runtime=runtime)
    assert active.total == 1 and active.cards[0].target.id == str(own.id)
    assert str(peer.id) not in active.model_dump_json()
    assert active.cards[0].description == "课堂进行中"
    assert (
        await resolve_target(runtime, active.cards[0].target) == f"/conversations?session={own.id}"
    )
    own.lifecycle, own.phase = "COMPLETED", "COMPLETED"
    await db.commit()
    completed = await learning_progress(LookupInput(content_type="LESSON"), {}, runtime=runtime)
    assert completed.cards[0].description == "课堂活动完成"
    assert "成绩" not in completed.model_dump_json() and "掌握" not in completed.model_dump_json()
    point = await db.scalar(
        select(KnowledgePoint.name)
        .join(RevisionKnowledgePoint)
        .where(RevisionKnowledgePoint.revision_id == revision.id)
    )
    assert point
    matches = await course_search(LookupInput(keyword=point), {}, runtime=runtime)
    assert any(str(revision.id) in card.id for card in matches.cards)
