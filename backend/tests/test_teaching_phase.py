"""T14 F1–F11: lesson phase/lifecycle, policy consumption, staleness rules."""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.modules.content.importer import import_package
from app.modules.content.package import load_package
from app.modules.identity.models import LearnerProfile
from app.modules.learning.models import LearningEvidence, LearningPolicySnapshot
from app.modules.teaching.models import (
    AgentRun,
    ConversationMessage,
    LessonSession,
    RunStatus,
    TeachingPhaseEvent,
)
from app.modules.teaching.phase import Phase, apply_phase_suggestion
from app.modules.teaching.service import (
    acquire_lease,
    create_session,
    ensure_policy_snapshot,
    finalize_run,
)
from tests.content_helpers import (
    chapter_file,
    copy_fixture_package,
    course_file,
    edit_json,
    revision_by_slug,
)
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    prepare_fixture_course,
    teaching_settings,
)

PASSWORD = "synthetic-pass-1"


async def _student(
    settings: Settings,
    name: str,
    *,
    grade: int = 2,
    stage: str = "PRIMARY_LOWER",
    proactive: bool = True,
):
    return await create_synthetic_user(
        settings,
        username=name,
        password=PASSWORD,
        stage=stage,
        grade=grade,
        proactive_guidance_enabled=proactive,
    )


async def _open(db, settings: Settings, user, chapter_id) -> LessonSession:
    return await create_session(db, settings=settings, user=user, chapter_id=chapter_id)


async def _event(client: httpx.AsyncClient, session_id, event: str, **payload) -> httpx.Response:
    body: dict = {"event": event}
    body.update(payload)
    return await client.post(
        f"/api/v1/lesson-sessions/{session_id}/events",
        json=body,
        headers=await csrf_headers(client),
    )


async def _count(db, model, **filters) -> int:
    statement = select(func.count()).select_from(model)
    for key, value in filters.items():
        statement = statement.where(getattr(model, key) == value)
    return int(await db.scalar(statement) or 0)


@pytest.mark.asyncio
async def test_enter_is_idempotent_across_tabs_and_refresh(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.enter.idem")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client_a = create_app_client(settings)
    client_b = create_app_client(settings)
    async with client_a, client_b:
        assert (await login(client_a, "t14.enter.idem", PASSWORD)).status_code == 200
        assert (await login(client_b, "t14.enter.idem", PASSWORD)).status_code == 200

        first = await _event(client_a, session_id, "ENTER")
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["proactive_opening"] == "TRIGGERED"
        assert body["phase"] == "ORIENT" and body["lifecycle"] == "ACTIVE"
        assert body["run"]["status"] in {"QUEUED", "RUNNING"}
        run_id = body["run"]["id"]

        # refresh / repeated ENTER never re-calls the tutor
        again = await _event(client_a, session_id, "ENTER")
        assert again.status_code == 200
        assert again.json()["run"]["id"] == run_id
        assert again.json()["proactive_opening"] == "ALREADY_OPENED"

        # two tabs racing on the same idempotency key converge on one run
        left, right = await asyncio.gather(
            _event(client_a, session_id, "ENTER"),
            _event(client_b, session_id, "ENTER"),
        )
        assert left.status_code == 200 and right.status_code == 200
        assert {left.json()["run"]["id"], right.json()["run"]["id"]} == {run_id}

    await content_session.rollback()
    assert await _count(content_session, AgentRun, session_id=session_id) == 1


@pytest.mark.asyncio
async def test_proactive_disabled_blocks_opening_but_not_student_question(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.proactive.off", proactive=False)
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.proactive.off", PASSWORD)).status_code == 200

        entered = await _event(client, session_id, "ENTER")
        assert entered.status_code == 200, entered.text
        body = entered.json()
        assert body["proactive_opening"] == "DISABLED_BY_PREFERENCE"
        assert body["run"] is None
        assert body["policy"]["proactive_opening_allowed"] is False
        assert body["phase"] == "ORIENT"

        asked = await _event(client, session_id, "ASK", message="我自己想问问规则是什么")
        assert asked.status_code == 200, asked.text
        assert asked.json()["run"]["status"] in {"QUEUED", "RUNNING"}
        assert asked.json()["phase"] == "ORIENT"

    await content_session.rollback()
    runs = (
        await content_session.scalars(select(AgentRun).where(AgentRun.session_id == session_id))
    ).all()
    assert len(runs) == 1
    assert runs[0].event == "ASK"


@pytest.mark.asyncio
async def test_resume_continues_persisted_progress_without_restart(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.resume")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.resume", PASSWORD)).status_code == 200
        assert (await _event(client, session_id, "ENTER")).status_code == 200
        explain = await _event(client, session_id, "START_EXPLAIN")
        assert explain.status_code == 200 and explain.json()["phase"] == "EXPLAIN"
        checked = await _event(client, session_id, "EXPLAIN_DONE")
        assert checked.status_code == 200 and checked.json()["phase"] == "CHECK"
        revision_after_check = checked.json()["phase_revision"]

        paused = await _event(client, session_id, "PAUSE")
        assert paused.status_code == 200
        assert paused.json()["lifecycle"] == "PAUSED"
        assert paused.json()["phase"] == "CHECK"  # lifecycle never moves phase
        while_paused = await _event(client, session_id, "CHECK_CORRECT")
        assert while_paused.status_code == 409  # nothing advances while paused

        resumed = await _event(client, session_id, "RESUME")
        assert resumed.status_code == 200
        assert resumed.json()["lifecycle"] == "ACTIVE"
        assert resumed.json()["phase"] == "CHECK"  # continues, does not restart
        assert resumed.json()["phase_revision"] == revision_after_check + 2

        # a fresh request (refresh) reads the same persisted state
        reread = await client.get(f"/api/v1/lesson-sessions/{session_id}/phase")
        assert reread.status_code == 200
        assert reread.json()["phase"] == "CHECK"
        assert reread.json()["lifecycle"] == "ACTIVE"

    await content_session.rollback()
    assert await _count(content_session, AgentRun, session_id=session_id) == 1
    events = (
        await content_session.scalars(
            select(TeachingPhaseEvent).where(TeachingPhaseEvent.session_id == session_id)
        )
    ).all()
    assert [row.event for row in events] == [
        "START_EXPLAIN",
        "EXPLAIN_DONE",
        "PAUSE",
        "RESUME",
    ]


@pytest.mark.asyncio
async def test_null_grade_still_produces_policy(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await prepare_fixture_course(content_session)
    junior_chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    junior_chapter_id = junior_chapter.chapter_id
    user = await create_synthetic_user(
        settings, username="t14.null.grade", password=PASSWORD, stage="JUNIOR", grade=None
    )
    session = await _open(content_session, settings, user, junior_chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.null.grade", PASSWORD)).status_code == 200
        entered = await _event(client, session_id, "ENTER")
        assert entered.status_code == 200, entered.text
        policy = entered.json()["policy"]
        assert policy["stage"] == "JUNIOR"
        assert policy["grade"] is None  # never invented
        assert policy["max_quiz_questions"] == 3
        assert "HARD" not in policy["allowed_difficulties"]
        assert policy["allowed_difficulties"][-1] == "MEDIUM"


@pytest.mark.asyncio
async def test_illegal_transitions_are_rejected_without_side_effects(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.illegal")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.illegal", PASSWORD)).status_code == 200
        unknown = await _event(client, session_id, "TELEPORT")
        assert unknown.status_code == 422

        wrong_phase = await _event(client, session_id, "CHECK_CORRECT")
        assert wrong_phase.status_code == 409
        practice_too_soon = await _event(client, session_id, "PRACTICE_DONE")
        assert practice_too_soon.status_code == 409
        not_paused = await _event(client, session_id, "RESUME_FROM_PAUSE")
        assert not_paused.status_code == 409

        no_message = await _event(client, session_id, "ASK")
        assert no_message.status_code == 422

    await content_session.rollback()
    assert await _count(content_session, TeachingPhaseEvent, session_id=session_id) == 0
    assert await _count(content_session, LearningEvidence, session_id=session_id) == 0
    assert await _count(content_session, AgentRun, session_id=session_id) == 0


@pytest.mark.asyncio
async def test_event_chain_to_practice_and_tutor_cannot_complete(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.chain")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.chain", PASSWORD)).status_code == 200
        assert (await _event(client, session_id, "ENTER")).status_code == 200
        assert (await _event(client, session_id, "START_EXPLAIN")).status_code == 200
        assert (await _event(client, session_id, "EXPLAIN_DONE")).status_code == 200

        wrong = await _event(client, session_id, "CHECK_INCORRECT", reference="quiz-1")
        assert wrong.status_code == 200
        assert wrong.json()["phase"] == "CHECK"  # remediation stays in CHECK
        assert wrong.json()["evidence"]["real_activities"] == 1

        right = await _event(client, session_id, "CHECK_CORRECT", reference="quiz-1b")
        assert right.status_code == 200
        body = right.json()
        assert body["phase"] == "PRACTICE"
        assert body["evidence"]["real_activities"] == 2
        assert body["evidence"]["correct_activities"] == 1
        assert body["evidence"]["evidence_level"] == "EMERGING"
        # young stage stays EASY regardless: a grade never forces hard work
        assert body["policy"]["allowed_difficulties"] == ["EASY"]

        # the tutor model may only *suggest*; COMPLETED is never writable by it
        assert apply_phase_suggestion(Phase.PRACTICE, "COMPLETED") is None
        assert apply_phase_suggestion(Phase.ORIENT, "CHECK") is Phase.CHECK
        assert apply_phase_suggestion(Phase.ORIENT, "NOT_A_PHASE") is None

        after = await client.get(f"/api/v1/lesson-sessions/{session_id}/phase")
        assert after.json()["phase"] == "PRACTICE"

    await content_session.rollback()
    kinds = (
        await content_session.scalars(
            select(LearningEvidence.kind).where(LearningEvidence.session_id == session_id)
        )
    ).all()
    assert list(kinds) == ["QUIZ_ANSWERED", "QUIZ_ANSWERED"]


@pytest.mark.asyncio
async def test_skip_records_skipped_without_faking_completion(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.skip")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.skip", PASSWORD)).status_code == 200
        assert (await _event(client, session_id, "ENTER")).status_code == 200
        assert (await _event(client, session_id, "START_EXPLAIN")).status_code == 200

        skipped = await _event(client, session_id, "SKIP_ACTIVITY", reference="practice-1")
        assert skipped.status_code == 200, skipped.text
        body = skipped.json()
        assert body["phase"] == "EXPLAIN"  # skip is not progress by itself
        assert body["evidence"]["skipped"] == 1
        assert body["evidence"]["real_activities"] == 0
        assert body["evidence"]["correct_activities"] == 0
        assert body["evidence"]["evidence_level"] == "NONE"

        # a skip is not a real activity: completion stays refused
        completed = await _event(client, session_id, "COMPLETE_REQUESTED")
        assert completed.status_code == 409

    await content_session.rollback()
    evidence = (
        await content_session.scalars(
            select(LearningEvidence).where(LearningEvidence.session_id == session_id)
        )
    ).all()
    assert [(row.kind, row.outcome) for row in evidence] == [("ACTIVITY_SKIPPED", "SKIPPED")]
    session_row = await content_session.scalar(
        select(LessonSession)
        .where(LessonSession.id == session_id)
        .execution_options(populate_existing=True)
    )
    assert session_row.phase == "EXPLAIN" and session_row.lifecycle == "ACTIVE"


@pytest.mark.asyncio
async def test_completion_needs_real_activity_and_explicit_event(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.complete")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.complete", PASSWORD)).status_code == 200
        assert (await _event(client, session_id, "ENTER")).status_code == 200
        too_early = await _event(client, session_id, "COMPLETE_REQUESTED")
        assert too_early.status_code == 409

        assert (await _event(client, session_id, "START_EXPLAIN")).status_code == 200
        assert (await _event(client, session_id, "EXPLAIN_DONE")).status_code == 200
        assert (await _event(client, session_id, "CHECK_CORRECT")).status_code == 200
        done = await _event(client, session_id, "COMPLETE_REQUESTED")
        assert done.status_code == 200, done.text
        assert done.json()["phase"] == "COMPLETED"
        assert done.json()["lifecycle"] == "COMPLETED"

        after = await _event(client, session_id, "START_EXPLAIN")
        assert after.status_code == 409  # completed lessons are read-only


@pytest.mark.asyncio
async def test_ask_question_keeps_phase_and_lesson_continues(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.ask")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.ask", PASSWORD)).status_code == 200
        assert (await _event(client, session_id, "ENTER")).status_code == 200
        explain = await _event(client, session_id, "START_EXPLAIN")
        assert explain.json()["phase_revision"] == 1

        ask = await _event(client, session_id, "ASK", message="今天天气怎么样，偏题一下")
        assert ask.status_code == 200
        assert ask.json()["phase"] == "EXPLAIN"
        assert ask.json()["phase_revision"] == 1  # off-topic questions do not move phase
        assert await _count_condition(content_session, AgentRun, session_id=session_id) == 2

        second_ask = await _event(client, session_id, "ASK", message="那我再问一个历史问题")
        assert second_ask.status_code == 200
        assert second_ask.json()["run"]["id"] != ask.json()["run"]["id"]

        continued = await _event(client, session_id, "EXPLAIN_DONE")
        assert continued.status_code == 200
        assert continued.json()["phase"] == "CHECK"

    await content_session.rollback()
    with_evidence = await _count(content_session, LearningEvidence, session_id=session_id)
    assert with_evidence == 0


async def _count_condition(db, model, **filters) -> int:
    statement = select(func.count()).select_from(model)
    for key, value in filters.items():
        statement = statement.where(getattr(model, key) == value)
    return int(await db.scalar(statement) or 0)


@pytest.mark.asyncio
async def test_stage_switch_stales_old_run_and_new_lesson_uses_new_policy(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    junior_chapter = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    junior_chapter_id = junior_chapter.chapter_id
    user = await _student(settings, "t14.stage.switch")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id
    user_id = user.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.stage.switch", PASSWORD)).status_code == 200
        entered = await _event(client, session_id, "ENTER")
        assert entered.status_code == 200
        old_run = entered.json()["run"]["id"]
        assert entered.json()["policy"]["stage"] == "PRIMARY_LOWER"

        await content_session.rollback()
        profile = await content_session.scalar(
            select(LearnerProfile).where(LearnerProfile.user_id == user_id)
        )
        patch = await client.patch(
            "/api/v1/me/profile",
            json={"stage": "JUNIOR", "grade": 7, "base_revision": profile.revision},
            headers=await csrf_headers(client),
        )
        assert patch.status_code == 200, patch.text

        # the PRIMARY_LOWER chapter is no longer visible to a JUNIOR learner:
        # the old lesson stops accepting writes instead of silently continuing.
        blocked = await _event(client, session_id, "ENTER")
        assert blocked.status_code == 409
        stale_state = await client.get(f"/api/v1/lesson-sessions/{session_id}/phase")
        assert stale_state.status_code == 200  # reads stay available (history)
        assert stale_state.json()["lifecycle"] == "STALE"

        # a new lesson opened in the new stage gets the new policy
        new_session_response = await client.post(
            "/api/v1/lesson-sessions",
            json={"chapter_id": str(junior_chapter_id)},
            headers=await csrf_headers(client),
        )
        assert new_session_response.status_code == 201, new_session_response.text
        new_session_id = new_session_response.json()["id"]
        opened = await _event(client, new_session_id, "ENTER")
        assert opened.status_code == 200, opened.text
        assert opened.json()["policy"]["stage"] == "JUNIOR"
        assert opened.json()["policy"]["max_quiz_questions"] == 3
        assert opened.json()["run"]["id"] != old_run

    await content_session.rollback()
    old = await content_session.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(old_run)))
    assert old.status == RunStatus.STALE.value
    assert old.stale_reason == "SESSION_BINDING_LOST"
    old_session = await content_session.scalar(
        select(LessonSession)
        .where(LessonSession.id == session_id)
        .execution_options(populate_existing=True)
    )
    assert old_session.lifecycle == "STALE"
    # the late answer for the old lesson was never written anywhere
    assert (
        await _count_condition(content_session, ConversationMessage, run_id=uuid.UUID(old_run)) == 0
    )


@pytest.mark.asyncio
async def test_profile_revision_supersedes_policy_on_same_stage(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.grade.bump")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id
    user_id = user.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.grade.bump", PASSWORD)).status_code == 200
        first = await _event(client, session_id, "ENTER")
        assert first.status_code == 200
        first_snapshot = first.json()["policy_snapshot_id"]
        first_run = first.json()["run"]["id"]

        await content_session.rollback()
        profile = await content_session.scalar(
            select(LearnerProfile).where(LearnerProfile.user_id == user_id)
        )
        patch = await client.patch(
            "/api/v1/me/profile",
            json={"grade": 3, "base_revision": profile.revision},
            headers=await csrf_headers(client),
        )
        assert patch.status_code == 200

        second = await _event(client, session_id, "ENTER")
        assert second.status_code == 200, second.text
        assert second.json()["policy_snapshot_id"] != first_snapshot
        assert second.json()["policy"]["grade"] == 3
        assert second.json()["run"]["id"] != first_run
        assert second.json()["proactive_opening"] == "TRIGGERED"

        again = await _event(client, session_id, "ENTER")
        assert again.json()["run"]["id"] == second.json()["run"]["id"]
        assert again.json()["proactive_opening"] == "ALREADY_OPENED"

    await content_session.rollback()
    old = await content_session.scalar(select(AgentRun).where(AgentRun.id == uuid.UUID(first_run)))
    assert old.status == RunStatus.STALE.value
    assert old.stale_reason == "POLICY_CHANGED"
    snapshots = (
        await content_session.scalars(
            select(LearningPolicySnapshot).where(LearningPolicySnapshot.session_id == session_id)
        )
    ).all()
    assert len(snapshots) == 2
    superseded = [row for row in snapshots if row.superseded_at is not None]
    assert len(superseded) == 1


@pytest.mark.asyncio
async def test_late_run_cannot_write_after_policy_change(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.late")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id
    user_id = user.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.late", PASSWORD)).status_code == 200
        entered = await _event(client, session_id, "ENTER")
        run_id = uuid.UUID(entered.json()["run"]["id"])

    await content_session.rollback()
    lease = await acquire_lease(content_session, run_id=run_id, ttl_seconds=60)
    assert lease is not None

    # the profile (and therefore the policy snapshot) moves while the tutor works
    profile = await content_session.scalar(
        select(LearnerProfile).where(LearnerProfile.user_id == user_id)
    )
    profile.revision += 1
    await content_session.commit()
    session_row = await content_session.scalar(
        select(LessonSession).where(LessonSession.id == session_id)
    )
    snapshot, created = await ensure_policy_snapshot(
        content_session, session=session_row, profile=profile
    )
    assert created is True
    await content_session.commit()

    status = await finalize_run(
        content_session,
        run_id=run_id,
        lease_token=lease,
        assistant={"message_markdown": "迟到的讲解", "phase_suggestion": "COMPLETED"},
    )
    assert status == RunStatus.STALE.value

    await content_session.rollback()
    run = await content_session.scalar(select(AgentRun).where(AgentRun.id == run_id))
    assert run.status == RunStatus.STALE.value
    assert run.stale_reason == "POLICY_CHANGED"
    assert await _count_condition(content_session, ConversationMessage, run_id=run_id) == 0
    session_after = await content_session.scalar(
        select(LessonSession)
        .where(LessonSession.id == session_id)
        .execution_options(populate_existing=True)
    )
    assert session_after.base_revision == 0
    assert session_after.phase == "ORIENT"  # a late suggestion never completes
    assert snapshot.evidence_level == "NONE"


@pytest.mark.asyncio
async def test_chapter_switch_stales_old_runs_and_keeps_progress(
    content_session, test_settings: Settings, tmp_path
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.chapter.switch")
    session_a = await _open(content_session, settings, user, revision.chapter_id)
    session_a_id = session_a.id

    # A second PRIMARY_LOWER chapter lands in a new synthetic release, so one
    # student can legitimately move between two visible lessons.
    revised = copy_fixture_package(tmp_path)
    edit_json(
        revised / "release.json",
        lambda data: data.__setitem__("release_key", "synthetic-t06-fixtures-t14-switch"),
    )
    course = json.loads(course_file(revised).read_text(encoding="utf-8"))
    extra = json.loads(json.dumps(course["chapters"][0]))
    extra["stable_slug"] = "ch03"
    extra["order_index"] = 3
    extra["title"] = "合成样例：切换章节后的新课"
    extra["content_file"] = "chapters/ch03.json"
    extra["source"]["source_path"] = "courses/t06-fixture-course/chapters/ch03.json"
    course["chapters"].append(extra)
    course_file(revised).write_text(
        json.dumps(course, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    document = json.loads(chapter_file(revised, "ch01").read_text(encoding="utf-8"))
    document["chapter"] = "ch03"
    (revised / "courses/t06-fixture-course/chapters/ch03.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    await import_package(content_session, load_package(revised), dry_run=False)
    ch03 = await revision_by_slug(content_session, "t06-fixture-course", "ch03", 1)
    assert ch03 is not None
    ch03_id = ch03.chapter_id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.chapter.switch", PASSWORD)).status_code == 200
        entered = await _event(client, session_a_id, "ENTER")
        assert entered.status_code == 200, entered.text
        stale_candidate = entered.json()["run"]["id"]

        # the student switches chapter: a new lesson is opened elsewhere
        switched = await client.post(
            "/api/v1/lesson-sessions",
            json={"chapter_id": str(ch03_id)},
            headers=await csrf_headers(client),
        )
        assert switched.status_code == 201, switched.text
        session_b_id = uuid.UUID(switched.json()["id"])

        # the old lesson keeps its progress and can be resumed later
        resumed = await _event(client, session_a_id, "RESUME")
        assert resumed.status_code == 200
        assert resumed.json()["lifecycle"] == "ACTIVE"
        assert resumed.json()["phase"] == "ORIENT"
        reopened = await _event(client, session_a_id, "ENTER")
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["run"]["id"] != stale_candidate
        assert reopened.json()["run"]["status"] in {"QUEUED", "RUNNING"}

    await content_session.rollback()
    old_run = await content_session.scalar(
        select(AgentRun).where(AgentRun.id == uuid.UUID(stale_candidate))
    )
    assert old_run.status == RunStatus.STALE.value
    assert old_run.stale_reason == "CHAPTER_SWITCH"
    old_session = await content_session.scalar(
        select(LessonSession)
        .where(LessonSession.id == session_a_id)
        .execution_options(populate_existing=True)
    )
    assert old_session.lifecycle != "STALE"  # progress was not destroyed
    assert old_session.phase == "ORIENT"
    assert (
        await _count_condition(content_session, ConversationMessage, session_id=session_b_id) == 0
    )


@pytest.mark.asyncio
async def test_content_revision_change_invalidates_bound_lesson(
    content_session, test_settings: Settings, tmp_path
):
    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session)
    user = await _student(settings, "t14.version")
    session = await _open(content_session, settings, user, revision.chapter_id)
    session_id = session.id

    client = create_app_client(settings)
    async with client:
        assert (await login(client, "t14.version", PASSWORD)).status_code == 200
        entered = await _event(client, session_id, "ENTER")
        assert entered.status_code == 200
        pending_run = entered.json()["run"]["id"]

        # publish revision 2 of the same chapter while the lesson is open
        revised = copy_fixture_package(tmp_path)
        edit_json(
            revised / "release.json",
            lambda data: data.__setitem__("release_key", "synthetic-t06-fixtures-v2"),
        )
        edit_json(
            course_file(revised),
            lambda data: data["chapters"][0].__setitem__("revision", 2),
        )
        document = json.loads(chapter_file(revised, "ch01").read_text(encoding="utf-8"))
        document["revision"] = 2
        chapter_file(revised, "ch01").write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        await import_package(content_session, load_package(revised), dry_run=False)

        blocked = await _event(client, session_id, "ENTER")
        assert blocked.status_code == 409, blocked.text
        state = await client.get(f"/api/v1/lesson-sessions/{session_id}/phase")
        assert state.json()["lifecycle"] == "STALE"
        assert state.json()["phase"] == "ORIENT"  # persisted, but no longer writable

    await content_session.rollback()
    run = await content_session.scalar(
        select(AgentRun).where(AgentRun.id == uuid.UUID(pending_run))
    )
    assert run.status == RunStatus.STALE.value
    assert run.stale_reason == "CONTENT_REVISION_CHANGED"
    assert (
        await _count_condition(content_session, AgentRun, session_id=session_id) == 1
    )  # no replacement run was created for the outdated revision
