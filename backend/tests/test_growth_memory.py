"""T18 K1–K11 (+QA14/QA20/QA21): evidence projection and revocable memory.

Real FastAPI app + real PostgreSQL test database. Quiz evidence is produced
through the real quiz routes with the T10 fixture gateway (explicit synthetic
draft): no model is asked to write a fact, and nothing here talks to Knodo.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.jobs import teaching_worker
from app.modules.content.importer import import_package
from app.modules.content.models import Chapter
from app.modules.content.package import load_package
from app.modules.learning.models import EvidenceItem, Observation
from app.modules.learning.projection import merge_learner_context
from app.modules.memory.models import MemoryEvent
from app.modules.memory.service import build_learner_context
from app.modules.teaching.context import build_session_context, build_teaching_request
from app.modules.teaching.service import create_session
from tests.content_helpers import FIXTURE_PACKAGE, revision_by_slug
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
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
# Exact field names that would turn a qualitative observation into a score, plus
# suffixes that make a score look like a percentage/mastery/IQ measure. The scan
# also rejects any percentage sign in any value, so the check is stricter than a
# substring search while still allowing explicit disclaimers such as
# "不是官方掌握度评分" to be phrased honestly.
FORBIDDEN_EXACT_KEYS = {
    "percent",
    "percentage",
    "mastery",
    "mastery_percent",
    "mastery_percentage",
    "iq",
    "iq_score",
    "intelligence",
    "personality",
    "trait",
    "traits",
}
FORBIDDEN_SUFFIXES = ("_percent", "_percentage", "_mastery", "_iq", "_iq_score")


def _walk(body, path=""):
    if isinstance(body, dict):
        for key, value in body.items():
            yield from _walk(value, f"{path}.{str(key).lower()}")
    elif isinstance(body, list):
        for item in body:
            yield from _walk(item, f"{path}[]")
    else:
        yield path, body


def _score_like_paths(body) -> list[tuple[str, object]]:
    problems: list[tuple[str, object]] = []
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


async def prepare_material(db, chapter_id):
    """Chapter material as the designer/assessment code sees it."""

    from app.modules.assessment.specs import load_chapter_material

    return await load_chapter_material(db, chapter_id=chapter_id)


async def _draft_with(db, settings: Settings, chapter_id, questions):
    """Create one AUTO_VALIDATED fixture draft for the chapter."""

    return await _auto_validated_draft(db, settings, chapter_id, questions)


def _questions_for(material, keys: list[str], *, objective: str | None = None):
    refs = _source_refs(material)
    objective_id = objective or (material.objectives[0] if material.objectives else "obj-1")
    return [_single_choice(key, objective_id, refs) for key in keys]


async def _evidence_count(db) -> int:
    return int(await db.scalar(select(func.count()).select_from(EvidenceItem)) or 0)


async def _project(client, expect: int = 200) -> dict:
    response = await client.post("/api/v1/growth/projection", headers=await csrf_headers(client))
    assert response.status_code == expect, response.text
    return response.json()


@pytest.mark.asyncio
async def test_projection_is_deduplicated_and_traceable(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    await _student(settings, "t18.dedup")
    material = await prepare_material(content_session, revision.chapter_id)
    await _draft_with(
        content_session, settings, revision.chapter_id, _questions_for(material, ["q1"])
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t18.dedup", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        first = await _answer(client, quiz["id"], question_id, "A", "t18-dedup-1")
        assert first.status_code == 200, first.text

        # Read-only API must not project anything by itself.
        before = await client.get("/api/v1/growth/overview")
        assert before.status_code == 200
        body = before.json()
        assert body["evidence_total"] == 0
        assert body["needs_projection"] is True
        assert body["observations"] == []
        assert await _evidence_count(content_session) == 0

        projected = await _project(client)
        assert projected["projection"]["evidence"]["inserted"] >= 1
        assert projected["evidence_total"] == projected["projection"]["evidence"]["inserted"]
        assert projected["needs_projection"] is False
        assert projected["observations"], projected

        # Re-projecting the same trusted events adds nothing.
        again = await _project(client)
        assert again["projection"]["evidence"]["inserted"] == 0
        assert again["projection"]["observations"]["created"] == 0
        assert again["evidence_total"] == projected["evidence_total"]
        assert [row["id"] for row in again["observations"]] == [
            row["id"] for row in projected["observations"]
        ]

        # The projected fact is traceable back to the original question/session.
        items = (
            await content_session.scalars(
                select(EvidenceItem).where(EvidenceItem.source_kind == "QUIZ_ANSWERED")
            )
        ).all()
        assert len(items) == 1
        single = await client.get(f"/api/v1/growth/evidence/{items[0].id}")
        assert single.status_code == 200
        payload = single.json()
        assert payload["source_kind"] == "QUIZ_ANSWERED"
        assert payload["outcome"] == "CORRECT"
        assert payload["source_ref"]["question_id"] == question_id
        assert payload["source_ref"]["quiz_session_id"] == quiz["id"]
        assert payload["rule_version"] == "k12.evidence.projection.v1"


@pytest.mark.asyncio
async def test_observations_are_qualitative_versioned_and_never_percentages(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    user = await _student(settings, "t18.observe", stage="JUNIOR", grade=8)
    material = await prepare_material(content_session, revision.chapter_id)
    objective = material.objectives[0]
    await _draft_with(
        content_session,
        settings,
        revision.chapter_id,
        _questions_for(material, ["o1", "o2", "o3"], objective=objective),
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t18.observe", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        questions = quiz["questions"]
        assert (
            await _answer(client, quiz["id"], questions[0]["id"], "A", "t18-obs-1")
        ).status_code == 200
        assert (
            await _answer(client, quiz["id"], questions[1]["id"], "B", "t18-obs-2")
        ).status_code == 200

        body = await _project(client)
        assert len(body["observations"]) == 1
        observation = body["observations"][0]
        assert observation["level"] == "EMERGING"
        assert observation["basis"]["answered"] == 2
        assert observation["basis"]["correct"] == 1
        assert observation["basis"]["effect_verified"] is False
        assert "仍需观察" in observation["statement"] or "仍在形成" in observation["statement"]
        assert observation["projection_revision"] == 1
        assert not any(fragment in observation["statement"] for fragment in ["%", "％"])

        # No mastery percentage / IQ / personality field anywhere in the body,
        # and no value that looks like a percentage.
        problems = _score_like_paths(body)
        assert problems == [], problems
        # The honest framing lives on every observation, not only the strongest one.
        assert "不是掌握度百分比" in observation["notice"]
        assert "未验证教学效果" in observation["notice"]

        # Answering again with the same objective changes the basis → new version,
        # and the previous version is kept but marked superseded.
        quiz2 = await _open_quiz(client, revision.chapter_id)
        await _answer(client, quiz2["id"], quiz2["questions"][0]["id"], "A", "t18-obs-3")
        after = await _project(client)
        assert after["observations"][0]["projection_revision"] == 2
        rows = (
            await content_session.scalars(
                select(Observation)
                .where(Observation.owner_user_id == user.id)
                .order_by(Observation.projection_revision)
            )
        ).all()
        assert [row.projection_revision for row in rows] == [1, 2]
        assert rows[0].superseded_at is not None
        assert rows[1].superseded_at is None


@pytest.mark.asyncio
async def test_insufficient_evidence_says_so_instead_of_concluding(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    await _student(settings, "t18.insufficient")
    material = await prepare_material(content_session, revision.chapter_id)
    await _draft_with(
        content_session, settings, revision.chapter_id, _questions_for(material, ["s1"])
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t18.insufficient", PASSWORD)
        empty = await _project(client)
        assert empty["evidence_total"] == 0
        assert empty["observations"] == []
        assert empty["insufficient_evidence"] is True
        assert "仍需观察" in empty["counts_not_effect_notice"]
        assert "不代表学习效果" in empty["counts_not_effect_notice"]

        quiz = await _open_quiz(client, revision.chapter_id)
        await _answer(client, quiz["id"], quiz["questions"][0]["id"], "B", "t18-ins-1")
        one = await _project(client)
        assert one["real_answers"] == 1
        assert one["correct_answers"] == 0
        assert one["observations"][0]["level"] == "EMERGING"
        assert one["insufficient_evidence"] is True


@pytest.mark.asyncio
async def test_memory_state_machine_keeps_history_and_cannot_be_revived(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    user = await _student(settings, "t18.memory", stage="JUNIOR", grade=8)
    material = await prepare_material(content_session, revision.chapter_id)
    await _draft_with(
        content_session,
        settings,
        revision.chapter_id,
        _questions_for(material, ["m1", "m2", "m3"]),
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t18.memory", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        # Wrong then right on the same question → the retry strategy candidate.
        assert (await _answer(client, quiz["id"], question_id, "B", "t18-mem-1")).status_code == 200
        assert (await _answer(client, quiz["id"], question_id, "A", "t18-mem-2")).status_code == 200

        body = await _project(client)
        candidates = body["memories"]
        assert len(candidates) == 1, candidates
        memory = candidates[0]
        assert memory["status"] == "CANDIDATE"
        assert memory["injection_status"] == "EXCLUDED"
        assert memory["revision"] == 1
        memory_id = memory["id"]

        async def act(action, revision_no, **extra):
            return await client.post(
                f"/api/v1/growth/memories/{memory_id}/events",
                json={"action": action, "base_revision": revision_no, **extra},
                headers=await csrf_headers(client),
            )

        confirmed = await act("CONFIRM", 1)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "ACTIVE"
        assert confirmed.json()["injection_status"] == "INJECTED"
        assert confirmed.json()["revision"] == 2

        edited = await act("EDIT", 2, statement="我会先看提示，然后再自己作答。")
        assert edited.status_code == 200, edited.text
        assert edited.json()["revision"] == 3
        history = edited.json()["history"]
        assert [row["action"] for row in history] == ["CREATE", "CONFIRM", "EDIT"]
        edit_event = history[-1]
        assert edit_event["statement_before"] == memory["statement"]
        assert edit_event["statement_after"] == "我会先看提示，然后再自己作答。"

        disputed = await act("DISPUTE", 3, reason="我其实没有这样做")
        assert disputed.status_code == 200
        assert disputed.json()["status"] == "DISPUTED"
        assert disputed.json()["injection_status"] == "EXCLUDED"

        # DISPUTED memories are not injected into the learner context.
        context = await build_learner_context(content_session, owner_user_id=user.id)
        assert all(item["id"] != memory_id for item in context)

        reconfirmed = await act("CONFIRM", 4)
        assert reconfirmed.status_code == 200
        context = await build_learner_context(content_session, owner_user_id=user.id)
        assert any(item["id"] == memory_id for item in context)

        forgotten = await act("FORGET", 5)
        assert forgotten.status_code == 200
        body_after = forgotten.json()
        assert body_after["status"] == "REMOVED"
        assert body_after["injection_status"] == "EXCLUDED"
        assert "不再注入教学上下文" in body_after["local_withdrawal_notice"]
        assert body_after["remote_residue"] == "NONE_LOCAL_ONLY"

        # Replaying the same old events (even with new evidence) must not revive it.
        again = await _project(client)
        still = [row for row in again["memories"] if row["id"] == memory_id]
        assert len(still) == 1
        assert still[0]["status"] == "REMOVED"
        assert len(again["memories"]) == 1
        context = await build_learner_context(content_session, owner_user_id=user.id)
        assert all(item["id"] != memory_id for item in context)

        # A forgotten memory is terminal.
        blocked = await act("CONFIRM", body_after["revision"])
        assert blocked.status_code == 409
        assert "MEMORY_FORGOTTEN" in blocked.json()["error"]["message"]

    events = (
        await content_session.scalars(
            select(MemoryEvent).where(MemoryEvent.candidate_id == uuid.UUID(memory_id))
        )
    ).all()
    assert len(events) == 6
    assert [row.action for row in events] == [
        "CREATE",
        "CONFIRM",
        "EDIT",
        "DISPUTE",
        "CONFIRM",
        "FORGET",
    ]


@pytest.mark.asyncio
async def test_stale_revision_is_rejected_without_partial_write(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    await _student(settings, "t18.stale", stage="JUNIOR", grade=8)
    material = await prepare_material(content_session, revision.chapter_id)
    await _draft_with(
        content_session,
        settings,
        revision.chapter_id,
        _questions_for(material, ["st1", "st2", "st3"]),
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t18.stale", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        await _answer(client, quiz["id"], question_id, "B", "t18-stale-1")
        await _answer(client, quiz["id"], question_id, "A", "t18-stale-2")
        memory = (await _project(client))["memories"][0]
        memory_id = memory["id"]

        first = await client.post(
            f"/api/v1/growth/memories/{memory_id}/events",
            json={"action": "CONFIRM", "base_revision": 1},
            headers=await csrf_headers(client),
        )
        assert first.status_code == 200 and first.json()["revision"] == 2

        stale = await client.post(
            f"/api/v1/growth/memories/{memory_id}/events",
            json={"action": "EDIT", "base_revision": 1, "statement": "过期写入不应生效"},
            headers=await csrf_headers(client),
        )
        assert stale.status_code == 409
        assert "MEMORY_REVISION_CONFLICT" in stale.json()["error"]["message"]

        detail = await client.get(f"/api/v1/growth/memories/{memory_id}")
        body = detail.json()
        assert body["revision"] == 2
        assert body["statement"] == memory["statement"]
        assert [row["action"] for row in body["history"]] == ["CREATE", "CONFIRM"]


@pytest.mark.asyncio
async def test_owner_isolation_and_csrf(content_session, test_settings: Settings):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    material = await prepare_material(content_session, revision.chapter_id)
    await _draft_with(
        content_session,
        settings,
        revision.chapter_id,
        _questions_for(material, ["iso1", "iso2", "iso3"]),
    )

    await _student(settings, "t18.student.a", stage="JUNIOR", grade=8)
    await _student(settings, "t18.student.b", stage="JUNIOR", grade=8)

    client_a = create_app_client(settings)
    async with client_a:
        await login(client_a, "t18.student.a", PASSWORD)
        quiz = await _open_quiz(client_a, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        await _answer(client_a, quiz["id"], question_id, "B", "t18-iso-1")
        await _answer(client_a, quiz["id"], question_id, "A", "t18-iso-2")
        a_body = await _project(client_a)
        memory_id = a_body["memories"][0]["id"]
        evidence_id = str(
            (
                await content_session.scalars(
                    select(EvidenceItem.id).where(EvidenceItem.source_kind == "QUIZ_ANSWERED")
                )
            ).first()
        )

        # CSRF is required for both write routes.
        no_csrf = await client_a.post("/api/v1/growth/projection")
        assert no_csrf.status_code == 403
        no_csrf_memory = await client_a.post(
            f"/api/v1/growth/memories/{memory_id}/events",
            json={"action": "CONFIRM", "base_revision": 1},
        )
        assert no_csrf_memory.status_code == 403

    client_b = create_app_client(settings)
    async with client_b:
        await login(client_b, "t18.student.b", PASSWORD)
        other_evidence = await client_b.get(f"/api/v1/growth/evidence/{evidence_id}")
        assert other_evidence.status_code == 404
        other_memory = await client_b.get(f"/api/v1/growth/memories/{memory_id}")
        assert other_memory.status_code == 404
        other_write = await client_b.post(
            f"/api/v1/growth/memories/{memory_id}/events",
            json={"action": "CONFIRM", "base_revision": 1},
            headers=await csrf_headers(client_b),
        )
        assert other_write.status_code == 404
        b_body = (await client_b.get("/api/v1/growth/overview")).json()
        assert b_body["evidence_total"] == 0
        assert b_body["memories"] == []
        # The other student's overview never contains A's memory id.
        assert memory_id not in json.dumps(b_body)


@pytest.mark.asyncio
async def test_learner_context_only_injects_valid_evidence_and_active_memory(
    content_session, test_settings: Settings
):
    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
    user = await _student(settings, "t18.context", stage="JUNIOR", grade=8)
    material = await prepare_material(content_session, revision.chapter_id)
    await _draft_with(
        content_session,
        settings,
        revision.chapter_id,
        _questions_for(material, ["c1", "c2", "c3"]),
    )
    chapter = await content_session.scalar(select(Chapter).where(Chapter.id == revision.chapter_id))
    session_context = build_session_context(
        chapter_slug=chapter.stable_slug,
        chapter_id=str(chapter.id),
        chapter_title=chapter.title,
        revision_number=revision.revision,
        revision_id=str(revision.id),
        stage=revision.stage,
        objectives=list(revision.objectives or []),
        blocks=list(revision.body or []),
    )

    def build_request(learner_context, base_revision: int):
        """Exactly what the worker does: build, then attach learner context."""

        request = build_teaching_request(
            session_id="00000000-0000-0000-0000-000000000001",
            context=session_context,
            operation=Operation.TEACH_TURN.value,
            student_input="继续讲",
            base_revision=base_revision,
            stage=revision.stage,
            grade=8,
            preferred_style="AUTO",
            fixture_allowance=None,
        )
        request["evidence"] = merge_learner_context(session_context, learner_context)
        return request

    client = create_app_client(settings)
    async with client:
        await login(client, "t18.context", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        question_id = quiz["questions"][0]["id"]
        await _answer(client, quiz["id"], question_id, "B", "t18-ctx-1")
        await _answer(client, quiz["id"], question_id, "A", "t18-ctx-2")
        memory = (await _project(client))["memories"][0]
        memory_id = memory["id"]

        # CANDIDATE is not injected yet.
        context = await build_learner_context(content_session, owner_user_id=user.id)
        assert context and all(item["id"] != memory_id for item in context)

        confirmed = await client.post(
            f"/api/v1/growth/memories/{memory_id}/events",
            json={"action": "CONFIRM", "base_revision": 1},
            headers=await csrf_headers(client),
        )
        assert confirmed.status_code == 200
        context = await build_learner_context(content_session, owner_user_id=user.id)
        assert any(
            item["id"] == memory_id and item["kind"] == "CONFIRMED_MEMORY" for item in context
        )
        assert all(
            item["kind"] in {"QUIZ_RESULT", "LEARNING_ACTIVITY", "CONFIRMED_MEMORY"}
            for item in context
        )

        request = build_request(context, 3)
        # The frozen request contract accepts the injected items (no new fields).
        assert default_registry().validate_request(Operation.TEACH_TURN, request) == []
        assert 0 < len(request["evidence"]) <= 12
        injected_ids = {item["id"] for item in request["evidence"]}
        assert memory_id in injected_ids
        assert set(session_context["allowed_evidence_ids"]) >= injected_ids

        # DISPUTED memories are excluded from the very next turn.
        disputed = await client.post(
            f"/api/v1/growth/memories/{memory_id}/events",
            json={"action": "DISPUTE", "base_revision": 2},
            headers=await csrf_headers(client),
        )
        assert disputed.status_code == 200
        disputed_context = await build_learner_context(content_session, owner_user_id=user.id)
        assert all(item["id"] != memory_id for item in disputed_context)
        disputed_request = build_request(disputed_context, 4)
        assert all(item["id"] != memory_id for item in disputed_request["evidence"])

        # FORGET keeps it out as well.
        removed = await client.post(
            f"/api/v1/growth/memories/{memory_id}/events",
            json={"action": "FORGET", "base_revision": 3},
            headers=await csrf_headers(client),
        )
        assert removed.status_code == 200
        final_context = await build_learner_context(content_session, owner_user_id=user.id)
        assert all(item["id"] != memory_id for item in final_context)
        final_request = build_request(final_context, 5)
        assert all(item["id"] != memory_id for item in final_request["evidence"])


async def test_worker_projects_before_building_the_turn(content_session, test_settings: Settings):
    """A tutor run is an event that projects; a read never does (K3/K4)."""

    settings = teaching_settings(test_settings)
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    revision = await revision_by_slug(content_session, "t06-fixture-course", "ch01", 1)
    user = await _student(settings, "t18.worker")
    material = await prepare_material(content_session, revision.chapter_id)
    await _draft_with(
        content_session, settings, revision.chapter_id, _questions_for(material, ["w1"])
    )

    client = create_app_client(settings)
    async with client:
        await login(client, "t18.worker", PASSWORD)
        quiz = await _open_quiz(client, revision.chapter_id)
        await _answer(client, quiz["id"], quiz["questions"][0]["id"], "A", "t18-work-1")
        assert await _evidence_count(content_session) == 0

        session = await create_session(
            content_session, settings=settings, user=user, chapter_id=revision.chapter_id
        )
        created = await client.post(
            f"/api/v1/lesson-sessions/{session.id}/turns",
            json={"message": "讲讲这道题", "idempotency_key": "t18-worker-key"},
            headers=await csrf_headers(client),
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["run"]["id"]
        status = await teaching_worker.execute_run(
            settings, client._transport.app.state.gateway, run_id
        )
        assert status == "SUCCEEDED"

    # The run projected the student's evidence before building the request.
    assert await _evidence_count(content_session) >= 1
    rows = (
        await content_session.scalars(
            select(EvidenceItem).where(EvidenceItem.owner_user_id == user.id)
        )
    ).all()
    assert rows, "worker must project the owner's trusted events"
