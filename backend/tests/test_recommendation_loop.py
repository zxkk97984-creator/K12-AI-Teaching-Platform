"""Student-facing recommendation loop, using actual owned quiz snapshots."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.identity.models import LearnerProfile
from app.modules.memory.automatic_models import PersonalMemoryItem, PersonalMemoryState
from app.modules.recommendation.decision import (
    CandidateChapter,
    DecisionInputs,
    LessonState,
    ObjectiveState,
    decide_next_step,
)
from app.modules.recommendation.interests import personal_interest_terms
from tests.test_recommendation import (
    FIXTURE_PACKAGE,
    PASSWORD,
    _answer,
    _draft,
    _material,
    _next_step,
    _open_quiz,
    _student,
    create_app_client,
    csrf_headers,
    import_package,
    load_package,
    login,
    revision_by_slug,
    teaching_settings,
)


@pytest.mark.asyncio
async def test_answer_updates_advice_and_correct_repeat_releases_old_mistake(
    content_session, test_settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    await _student(settings, "loop.answer")
    material = await _material(content_session, revision.chapter_id)
    await _draft(content_session, settings, revision.chapter_id, material, ["loop-q"])
    async with create_app_client(settings) as client:
        await login(client, "loop.answer", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        question = quiz["questions"][0]
        response = await _answer(client, quiz["id"], question["id"], "B", "loop-wrong")
        assert response.status_code == 200
        advice = await _next_step(client)
        assert advice["snapshot_state"] == "CURRENT"
        assert advice["needs_projection"] is False
        assert advice["primary"]["kind"] == "REVIEW_MISTAKE"
        assert advice["primary"]["action"]["quiz_session_id"] == quiz["id"]
        assert advice["primary"]["action"]["question_position"] == 0
        assert advice["primary"]["action"]["quiz_status"] == "COMPLETED"
        assert advice["primary"]["action"]["quiz_answered"] == 1
        assert advice["primary"]["action"]["quiz_title"]
        assert quiz["draft_id"]
        assert advice["primary"]["source"]["question_id"] == question["id"]
        assert "correct_answer" not in str(advice)

        replay = await _answer(client, quiz["id"], question["id"], "B", "loop-wrong")
        assert replay.status_code == 200
        assert replay.json()["idempotent_replay"] is True
        unchanged = await _next_step(client)
        assert unchanged["basis"]["real_answers"] == 1
        assert unchanged["inputs_hash"] == advice["inputs_hash"]

        repeated = await client.post(
            f"/api/v1/quiz-sessions/{quiz['id']}/repeat",
            json={},
            headers=await csrf_headers(client),
        )
        assert repeated.status_code == 201, repeated.text
        retry = repeated.json()
        assert (
            await _answer(client, retry["id"], retry["questions"][0]["id"], "A", "loop-correct")
        ).status_code == 200
        updated = await _next_step(client)
        assert updated["snapshot_state"] == "CURRENT"
        assert updated["primary"]["kind"] != "REVIEW_MISTAKE"
        assert updated["inputs_hash"] != advice["inputs_hash"]


@pytest.mark.asyncio
async def test_correcting_one_question_keeps_the_other_unresolved_mistake(
    content_session, test_settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    await _student(settings, "loop.remaining", stage="JUNIOR", grade=8)
    await _draft(
        content_session,
        settings,
        revision.chapter_id,
        await _material(content_session, revision.chapter_id),
        ["first", "second", "third"],
    )
    async with create_app_client(settings) as client:
        await login(client, "loop.remaining", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        first, second, third = [question["id"] for question in quiz["questions"]]
        for question_id, answer, key in [
            (first, "B", "loop-first-wrong"),
            (second, "B", "loop-second-wrong"),
            (first, "A", "loop-first-fixed"),
            (third, "A", "loop-third-correct"),
        ]:
            response = await _answer(client, quiz["id"], question_id, answer, key)
            assert response.status_code == 200, response.text
        advice = await _next_step(client)
        assert advice["primary"]["kind"] == "REVIEW_MISTAKE"
        assert advice["primary"]["source"]["question_id"] == second
        assert advice["primary"]["action"]["question_position"] == 1
        assert "1 道题" in advice["primary"]["reason"]


@pytest.mark.asyncio
async def test_old_stage_answers_are_not_recommended_after_stage_change(
    content_session, test_settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    user = await _student(settings, "loop.stage")
    await _draft(
        content_session,
        settings,
        revision.chapter_id,
        await _material(content_session, revision.chapter_id),
        ["stage-q"],
    )
    async with create_app_client(settings) as client:
        await login(client, "loop.stage", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        await _answer(client, quiz["id"], quiz["questions"][0]["id"], "B", "stage-wrong")
        await client.post("/api/v1/recommendation/refresh", headers=await csrf_headers(client))
        profile = await content_session.scalar(
            select(LearnerProfile).where(LearnerProfile.user_id == user.id)
        )
        profile.stage, profile.grade = "JUNIOR", 8
        await content_session.commit()
        advice = await _next_step(client)
        assert advice["primary"]["kind"] != "REVIEW_MISTAKE"
        assert advice["basis"]["real_answers"] == 0


def test_current_mistake_wins_over_old_consistent_objective_and_lesson():
    decision = decide_next_step(
        DecisionInputs(
            stage="JUNIOR",
            grade=8,
            preferred_style="AUTO",
            active_lesson=LessonState("lesson", "chapter", "章节", "REFLECT", "ACTIVE"),
            objectives=(
                ObjectiveState("old", 10, 0, "CONSISTENT"),
                ObjectiveState("new", 3, 1, "CONSISTENT"),
            ),
            candidates=(CandidateChapter("chapter", "章节", "课程", 1, "JUNIOR"),),
            real_answers=13,
        )
    )
    assert decision["primary"]["kind"] == "REVIEW_MISTAKE"
    assert decision["primary"]["action"]["objective_id"] == "new"


@pytest.mark.asyncio
async def test_saved_answer_survives_recommendation_failure(
    content_session, test_settings, monkeypatch
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    await _student(settings, "loop.failure")
    await _draft(
        content_session,
        settings,
        revision.chapter_id,
        await _material(content_session, revision.chapter_id),
        ["failure-q"],
    )

    async def unavailable(*args, **kwargs):
        raise RuntimeError("recommendation unavailable")

    monkeypatch.setattr("app.modules.recommendation.service.refresh_snapshot", unavailable)
    async with create_app_client(settings) as client:
        await login(client, "loop.failure", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        answer = await _answer(client, quiz["id"], quiz["questions"][0]["id"], "A", "loop-saved")
        assert answer.status_code == 200, answer.text
        assert answer.json()["is_correct"] is True
        result = await client.get(f"/api/v1/quiz-sessions/{quiz['id']}/result")
        assert result.status_code == 200
        assert result.json()["correct"] == 1


@pytest.mark.asyncio
async def test_personal_interests_respect_owner_correction_forget_expiry_and_switch(
    content_session, test_settings
):
    db = content_session
    user = await _student(test_settings, "loop.interest")
    other = await _student(test_settings, "loop.other")
    state = PersonalMemoryState(owner_user_id=user.id, use_enabled=True)
    memory = PersonalMemoryItem(
        owner_user_id=user.id,
        key="interest",
        category="INTEREST",
        statement="用户喜欢机器人",
        observed_at=datetime.now(UTC),
        manual=True,
        sources=[],
    )
    unrelated = PersonalMemoryItem(
        owner_user_id=other.id,
        key="interest",
        category="INTEREST",
        statement="用户喜欢 Python",
        observed_at=datetime.now(UTC),
        manual=True,
        sources=[],
    )
    db.add_all([state, memory, unrelated])
    await db.commit()
    candidates = (
        CandidateChapter("robot", "机器人", "人工智能", 1, "PRIMARY_LOWER"),
        CandidateChapter("python", "Python", "编程", 2, "PRIMARY_LOWER"),
    )

    async def read():
        return await personal_interest_terms(db, owner_user_id=user.id, candidates=candidates)

    interest, sources = await read()
    assert "机器" in interest and "python" not in interest
    assert sources == (f"personal-memory:{memory.id}:v1",)
    memory.statement, memory.revision = "用户喜欢 Python", 2
    await db.commit()
    interest, sources = await read()
    assert "python" in interest and "机器" not in interest
    assert sources == (f"personal-memory:{memory.id}:v2",)
    for field, value, restore in [
        ("status", "REMOVED", "ACTIVE"),
        ("valid_until", datetime.now(UTC) - timedelta(seconds=1), None),
        ("category", "PREFERENCE", "INTEREST"),
    ]:
        setattr(memory, field, value)
        await db.commit()
        assert await read() == ((), ())
        setattr(memory, field, restore)
    state.use_enabled = False
    await db.commit()
    assert await read() == ((), ())


@pytest.mark.asyncio
async def test_restored_inputs_reactivate_their_existing_snapshot(content_session, test_settings):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _student(settings, "loop.restore")
    async with create_app_client(settings) as client:
        await login(client, "loop.restore", PASSWORD)
        headers = await csrf_headers(client)
        original = (await client.post("/api/v1/recommendation/refresh", headers=headers)).json()
        subject = original["primary"]["subject_key"]
        assert (
            await client.post(
                "/api/v1/recommendation/feedback",
                headers=headers,
                json={"subject_key": subject, "action": "IGNORE", "base_revision": 0},
            )
        ).status_code == 200
        ignored = (await client.post("/api/v1/recommendation/refresh", headers=headers)).json()
        assert ignored["snapshot_state"] == "CURRENT"
        assert (
            await client.post(
                "/api/v1/recommendation/feedback",
                headers=headers,
                json={"subject_key": subject, "action": "RESTORE", "base_revision": 1},
            )
        ).status_code == 200
        restored = (await client.post("/api/v1/recommendation/refresh", headers=headers)).json()
        assert restored["snapshot_state"] == "CURRENT"
        assert restored["snapshot"]["id"] == original["snapshot"]["id"]
        assert restored["projection"]["created"] is False
