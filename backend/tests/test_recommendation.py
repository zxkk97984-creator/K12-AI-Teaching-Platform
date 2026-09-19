"""T19 L1–L11 (+QA20/QA22): one event-driven next-step decision.

Real FastAPI app + real PostgreSQL test database. Evidence comes from the real
quiz routes (T10 fixture gateway for the *questions* only); recommendations are
computed by the local rule engine — no model, no Knodo call.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.jobs import teaching_worker
from app.modules.content.importer import import_package
from app.modules.content.models import ChapterReviewState
from app.modules.content.package import load_package
from app.modules.learning.models import EvidenceItem
from app.modules.recommendation.models import (
    RecommendationFeedback,
    RecommendationFeedbackEvent,
    RecommendationSnapshot,
)
from app.modules.recommendation.service import assemble_inputs
from app.modules.teaching.models import LessonSession
from app.modules.teaching.service import create_session
from tests.content_helpers import FIXTURE_PACKAGE, revision_by_slug
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    prepare_fixture_course,
    teaching_settings,
)
from tests.test_quiz_sessions import (
    _answer,
    _auto_validated_draft,
    _open_quiz,
    _single_choice,
    _source_refs,
)

PASSWORD = "synthetic-pass-1"
FORBIDDEN_EXACT_KEYS = {
    "percent",
    "percentage",
    "mastery",
    "rank",
    "ranking",
    "leaderboard",
    "iq",
    "iq_score",
    "intelligence",
    "personality",
    "trait",
    "score_percent",
}
FORBIDDEN_SUFFIXES = ("_percent", "_percentage", "_mastery", "_rank", "_iq")


def _walk(body, path=""):
    if isinstance(body, dict):
        for key, value in body.items():
            yield from _walk(value, f"{path}.{str(key).lower()}")
    elif isinstance(body, list):
        for item in body:
            yield from _walk(item, f"{path}[]")
    else:
        yield path, body


def _forbidden_paths(body) -> list[tuple[str, object]]:
    problems = []
    for path, value in _walk(body):
        leaf = path.rsplit(".", 1)[-1]
        if leaf in FORBIDDEN_EXACT_KEYS or leaf.endswith(FORBIDDEN_SUFFIXES):
            problems.append((path, value))
        if isinstance(value, str) and ("%" in value or "％" in value):
            problems.append((path, value))
    return problems


async def _student(settings: Settings, name: str, *, stage: str = "PRIMARY_LOWER", grade: int = 2):
    return await create_synthetic_user(
        settings, username=name, password=PASSWORD, stage=stage, grade=grade
    )


async def _material(db, chapter_id):
    from app.modules.assessment.specs import load_chapter_material

    return await load_chapter_material(db, chapter_id=chapter_id)


async def _draft(db, settings, chapter_id, material, keys):
    objective = material.objectives[0] if material.objectives else "obj-1"
    questions = [_single_choice(key, objective, _source_refs(material)) for key in keys]
    return await _auto_validated_draft(db, settings, chapter_id, questions)


async def _count(db, model) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


async def _next_step(client) -> dict:
    response = await client.get("/api/v1/recommendation/next-step")
    assert response.status_code == 200, response.text
    return response.json()


async def _refresh(client) -> dict:
    response = await client.post(
        "/api/v1/recommendation/refresh", headers=await csrf_headers(client)
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_read_is_pure_and_events_change_the_decision(
    content_session, test_settings: Settings
):
    """QA22 + QA20: ten GETs write nothing; a real wrong answer changes it."""

    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    await _student(settings, "t19.pure")
    material = await _material(content_session, revision.chapter_id)
    await _draft(content_session, settings, revision.chapter_id, material, ["p1"])

    client = create_app_client(settings)
    async with client:
        await login(client, "t19.pure", PASSWORD)

        # Cold start: no evidence yet, and the page says so.
        first = await _next_step(client)
        assert first["cold_start"] is True
        assert first["snapshot_state"] == "NOT_PROJECTED"
        assert first["needs_refresh"] is True
        assert first["primary"]["kind"] == "START_COURSE"
        assert "不是根据已学历史推断" in first["primary"]["reason"]
        assert first["primary"]["source"]["type"] == "CHAPTER"
        assert not _forbidden_paths(first), _forbidden_paths(first)

        snapshots_before = await _count(content_session, RecommendationSnapshot)
        for _ in range(10):
            await _next_step(client)
        assert await _count(content_session, RecommendationSnapshot) == snapshots_before == 0
        assert await _count(content_session, EvidenceItem) == 0

        # A real wrong answer is a real event.
        quiz = await _open_quiz(client, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        answered = await _answer(client, quiz["id"], question_id, "B", "t19-wrong-1")
        assert answered.status_code == 200, answered.text
        assert answered.json()["is_correct"] is False

        # Before the event-driven projection the read model says so honestly.
        pending = await _next_step(client)
        assert pending["needs_projection"] is True
        assert pending["cold_start"] is True

        # A refresh is an event: it projects the evidence and stores the decision.
        refreshed = await _refresh(client)
        assert refreshed["projection"]["created"] is True
        assert refreshed["snapshot_state"] == "CURRENT"
        assert refreshed["needs_refresh"] is False
        assert refreshed["primary"]["kind"] == "REVIEW_MISTAKE"
        assert await _count(content_session, RecommendationSnapshot) == 1

        after_event = await _next_step(client)
        assert after_event["needs_projection"] is False
        assert after_event["cold_start"] is False
        assert after_event["primary"]["kind"] == "REVIEW_MISTAKE"
        assert after_event["primary"]["evidence_ids"], after_event["primary"]
        assert after_event["rule_version"] == "k12.recommendation.rule.v1"
        assert after_event["effect_verified"] is False

        # README of the snapshot can be traced back to the original evidence.
        snapshot_id = refreshed["snapshot"]["id"]
        detail = await client.get(f"/api/v1/recommendation/snapshots/{snapshot_id}")
        assert detail.status_code == 200
        trace = detail.json()["trace"]
        assert trace["evidence_ids"], trace
        assert trace["rule_version"] == "k12.recommendation.rule.v1"

        # Identical inputs must not create another snapshot (L6).
        again = await _refresh(client)
        assert again["projection"]["created"] is False
        assert await _count(content_session, RecommendationSnapshot) == 1


@pytest.mark.asyncio
async def test_hints_and_skips_are_not_mastery_and_never_raise_difficulty(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    await _student(settings, "t19.hint")
    material = await _material(content_session, revision.chapter_id)
    await _draft(content_session, settings, revision.chapter_id, material, ["h1"])

    client = create_app_client(settings)
    async with client:
        await login(client, "t19.hint", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        hint = await client.post(
            f"/api/v1/quiz-sessions/{quiz['id']}/questions/{question_id}/hints",
            json={"level": 1, "idempotency_key": "t19-hint-1"},
            headers=await csrf_headers(client),
        )
        assert hint.status_code == 200, hint.text

        # Project first (a refresh is the event path), then read.
        await _refresh(client)
        body = await _next_step(client)
        # Only a hint exists: still no mastery claim, and no harder content.
        assert body["primary"]["kind"] in ("START_COURSE", "CONTINUE_COURSE")
        assert body["cold_start"] is True
        assert body["basis"]["hints_or_skips_only"] is True
        item = body["primary"]
        assert "difficulty" not in json.dumps(item)
        assert "HARD" not in json.dumps(body)
        assert not _forbidden_paths(body), _forbidden_paths(body)


@pytest.mark.asyncio
async def test_decision_matches_the_teaching_phase_state(content_session, test_settings: Settings):
    """L1: one decision — the lesson surface and /learn agree."""

    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session, chapter_slug="ch01")
    user = await _student(settings, "t19.lesson")
    session = await create_session(
        content_session, settings=settings, user=user, chapter_id=revision.chapter_id
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t19.lesson", PASSWORD)
        for phase, expected in (
            ("ORIENT", "开始这一节的讲解"),
            ("EXPLAIN", "看完讲解，进入检查"),
            ("CHECK", "完成本节的理解检查"),
            ("PRACTICE", "完成这一节的练习"),
            ("REFLECT", "复盘并结束本节"),
        ):
            session.phase = phase
            session.lifecycle = "ACTIVE"
            await content_session.commit()
            body = await _next_step(client)
            assert body["primary"]["kind"] == "CONTINUE_LESSON"
            assert body["primary"]["title"] == expected
            assert body["primary"]["action"]["type"] == "OPEN_LESSON"
            assert body["primary"]["source"]["phase"] == phase

        # Paused still wins over new content, with the honest continuation copy.
        session.lifecycle = "PAUSED"
        await content_session.commit()
        paused = await _next_step(client)
        assert paused["primary"]["title"] == "继续之前暂停的这一节"

        # The same stored state drives the lesson API, so the two cannot disagree.
        phase_body = await client.get(f"/api/v1/lesson-sessions/{session.id}/phase")
        assert phase_body.status_code == 200
        assert phase_body.json()["phase"] == session.phase
        assert phase_body.json()["lifecycle"] == session.lifecycle


@pytest.mark.asyncio
async def test_withdrawn_evidence_and_disputed_memory_stop_participating(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    # JUNIOR allows 3 questions, so a wrong answer stays ACTIVE long enough for
    # the retry pattern that derives the memory candidate.
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    user = await _student(settings, "t19.withdrawn", stage="JUNIOR", grade=8)
    material = await _material(content_session, revision.chapter_id)
    await _draft(content_session, settings, revision.chapter_id, material, ["w1", "w2", "w3"])

    client = create_app_client(settings)
    async with client:
        await login(client, "t19.withdrawn", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        assert (
            await _answer(client, quiz["id"], question_id, "B", "t19-with-1")
        ).status_code == 200
        assert (
            await _answer(client, quiz["id"], question_id, "A", "t19-with-2")
        ).status_code == 200

        refreshed = await _refresh(client)
        assert refreshed["primary"]["kind"] == "REVIEW_MISTAKE"

        # The derived candidate must be *confirmed* by the student before it can
        # be part of any decision input (CANDIDATE is excluded by T18 design).
        memories = (await client.get("/api/v1/growth/memories")).json()["items"]
        candidates = [item for item in memories if item["status"] == "CANDIDATE"]
        assert candidates, memories
        candidate = candidates[0]
        confirmed = await client.post(
            f"/api/v1/growth/memories/{candidate['id']}/events",
            json={"action": "CONFIRM", "base_revision": candidate["revision"]},
            headers=await csrf_headers(client),
        )
        assert confirmed.status_code == 200, confirmed.text
        await _refresh(client)
        first = await _next_step(client)
        assert first["basis"]["active_memory_ids"] == [candidate["id"]]

        # DISPUTED memory drops out of the basis immediately (no new decision input).
        disputed = await client.post(
            f"/api/v1/growth/memories/{candidate['id']}/events",
            json={"action": "DISPUTE", "base_revision": confirmed.json()["revision"]},
            headers=await csrf_headers(client),
        )
        assert disputed.status_code == 200, disputed.text
        after_dispute = await _next_step(client)
        assert after_dispute["basis"]["active_memory_ids"] == []

        # Withdraw the chapter revision: its evidence no longer participates.
        review_state = await content_session.scalar(
            select(ChapterReviewState).where(ChapterReviewState.revision_id == revision.id)
        )
        # Withdrawal carries an audit trail (the DB constraint requires it).
        review_state.publication_status = "WITHDRAWN"
        review_state.withdrawn_by = "t19.test.reviewer"
        review_state.withdrawn_at = datetime.now(UTC)
        await content_session.commit()
        withdrawn = await _next_step(client)
        assert withdrawn["basis"]["evidence_ids"] == []
        assert withdrawn["primary"]["kind"] != "REVIEW_MISTAKE"
        assert withdrawn["cold_start"] is True

    # The service-level filter is what produced that: the rows still exist.
    assert await _count(content_session, EvidenceItem) > 0
    inputs = await assemble_inputs(content_session, owner_user_id=user.id, settings=settings)
    assert inputs.evidence_ids == ()
    assert inputs.active_memory_ids == ()


async def test_feedback_round_trip_and_stale_rejection(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _student(settings, "t19.feedback")

    client = create_app_client(settings)
    async with client:
        await login(client, "t19.feedback", PASSWORD)
        body = await _refresh(client)
        subject = body["primary"]["subject_key"]

        first = await client.post(
            "/api/v1/recommendation/feedback",
            json={
                "subject_key": subject,
                "action": "IGNORE",
                "base_revision": 0,
                "reason": "先不做",
            },
            headers=await csrf_headers(client),
        )
        assert first.status_code == 200, first.text
        assert first.json()["state"] == "IGNORED"
        assert first.json()["revision"] == 1

        ignored = await _next_step(client)
        assert ignored["primary"]["kind"] == "ALL_IGNORED"
        assert subject in ignored["ignored_subjects"]

        # Repeating the same action adds no revision and no event.
        repeat = await client.post(
            "/api/v1/recommendation/feedback",
            json={"subject_key": subject, "action": "IGNORE", "base_revision": 1},
            headers=await csrf_headers(client),
        )
        assert repeat.status_code == 200 and repeat.json()["revision"] == 1
        assert await _count(content_session, RecommendationFeedbackEvent) == 1

        stale = await client.post(
            "/api/v1/recommendation/feedback",
            json={"subject_key": subject, "action": "RESTORE", "base_revision": 99},
            headers=await csrf_headers(client),
        )
        assert stale.status_code == 409
        assert "RECOMMENDATION_FEEDBACK_CONFLICT" in stale.json()["error"]["message"]
        row = await content_session.scalar(
            select(RecommendationFeedback).where(RecommendationFeedback.subject_key == subject)
        )
        assert row.state == "IGNORED" and row.revision == 1

        no_csrf = await client.post(
            "/api/v1/recommendation/feedback",
            json={"subject_key": subject, "action": "RESTORE", "base_revision": 1},
        )
        assert no_csrf.status_code == 403

        restored = await client.post(
            "/api/v1/recommendation/feedback",
            json={"subject_key": subject, "action": "RESTORE", "base_revision": 1},
            headers=await csrf_headers(client),
        )
        assert restored.status_code == 200
        assert restored.json()["state"] == "ACTIVE"
        assert restored.json()["revision"] == 2
        assert [row["action"] for row in restored.json()["history"]] == ["IGNORE", "RESTORE"]

        back = await _next_step(client)
        assert back["primary"]["kind"] != "ALL_IGNORED"


@pytest.mark.asyncio
async def test_owner_isolation_and_csrf(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    await _student(settings, "t19.owner.a")
    await _student(settings, "t19.owner.b")

    client_a = create_app_client(settings)
    async with client_a:
        await login(client_a, "t19.owner.a", PASSWORD)
        snapshot_id = (await _refresh(client_a))["snapshot"]["id"]
        no_csrf = await client_a.post("/api/v1/recommendation/refresh")
        assert no_csrf.status_code == 403

    client_b = create_app_client(settings)
    async with client_b:
        await login(client_b, "t19.owner.b", PASSWORD)
        denied = await client_b.get(f"/api/v1/recommendation/snapshots/{snapshot_id}")
        assert denied.status_code == 404
        b_body = await _next_step(client_b)
        assert b_body["snapshot"] is None or b_body["snapshot"]["id"] != snapshot_id
        assert snapshot_id not in json.dumps(b_body)


@pytest.mark.asyncio
async def test_worker_recomputes_the_snapshot_on_a_run(content_session, test_settings: Settings):
    """An event (tutor run) refreshes the stored projection; GET still does not."""

    settings = teaching_settings(test_settings)
    revision = await prepare_fixture_course(content_session, chapter_slug="ch01")
    user = await _student(settings, "t19.worker")
    session = await create_session(
        content_session, settings=settings, user=user, chapter_id=revision.chapter_id
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t19.worker", PASSWORD)
        assert await _count(content_session, RecommendationSnapshot) == 0
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "开始吧", "idempotency_key": "t19-worker-1"},
            headers=await csrf_headers(client),
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["run"]["id"]
        status = await teaching_worker.execute_run(
            settings, client._transport.app.state.gateway, run_id
        )
        assert status == "SUCCEEDED"

    # Exactly one snapshot was produced by the event…
    assert await _count(content_session, RecommendationSnapshot) == 1
    stored = await content_session.scalar(select(RecommendationSnapshot))
    assert stored.primary_item["kind"] == "CONTINUE_LESSON"
    assert stored.effect_verified is False
    # …and the run itself still owns the lesson session state it wrote.
    lesson = await content_session.scalar(
        select(LessonSession).where(LessonSession.id == session.id)
    )
    assert lesson is not None
