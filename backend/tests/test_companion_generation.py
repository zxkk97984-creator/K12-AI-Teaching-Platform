"""Private twenty-question groups, durable batching and owner boundaries."""

import asyncio
import copy

import httpx
import pytest

from app.main import create_app
from app.modules.identity.models import Stage
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import csrf_headers


def test_book_context_is_versioned_and_uses_packaged_paragraphs():
    from app.modules.learning.study_books import book_sections
    from app.modules.learning.study_content import bind_scene

    version, sections = book_sections("python3")
    scene = {
        "content_kind": "BOOK",
        "content_id": "python3",
        "content_version": version,
        "section_index": 0,
        "selected_text": "untrusted replacement for the textbook",
    }
    for stage in ("PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"):
        bound = bind_scene(scene, stage=stage)
        assert bound["selected_text"] in sections[0]
        assert "untrusted replacement" not in bound["selected_text"]
    with pytest.raises(ValueError, match="版本已变化"):
        bind_scene({**scene, "content_version": "old"}, stage="JUNIOR")
    with pytest.raises(ValueError, match="位置无效"):
        bind_scene({**scene, "section_index": -1}, stage="JUNIOR")


async def wait_job(client, job_id):
    for _ in range(100):
        job = (await client.get(f"/api/v1/quiz-generation-jobs/{job_id}")).json()["job"]
        if job["status"] not in ("QUEUED", "RUNNING"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("generation did not finish")


@pytest.mark.asyncio
async def test_followup_only_receives_feedback_for_an_answered_question(
    content_session, test_settings
):
    from app.jobs import teaching_worker
    from tests.teaching_helpers import teaching_settings

    settings = teaching_settings(test_settings, assessment_autorun=True)
    await create_synthetic_user(
        settings,
        username="feedback.companion",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=8,
    )
    app = create_app(settings)
    original = app.state.gateway.invoke
    captured = []

    async def capture(operation, payload, **options):
        result = await original(operation, payload, **options)
        if operation == "QUIZ_DRAFT":
            output = copy.deepcopy(result.output)
            for index, question in enumerate(output["questions"]):
                question["explanation"] = f"private-feedback-marker-{index}"
            return result.model_copy(update={"output": output})
        captured.append(payload["student_input"])
        return result

    app.state.gateway.invoke = capture
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "feedback.companion", "synthetic-pass-1")
        headers = await csrf_headers(client)
        conversation = (await client.post("/api/v1/conversations", json={}, headers=headers)).json()
        generated = await client.post(
            "/api/v1/quiz-generation-jobs",
            json={
                "conversation_id": conversation["id"],
                "student_request": "围绕数据分类生成2题",
                "knowledge_point": "数据分类",
                "ordinary_question_count": 2,
                "idempotency_key": "feedback-context-quiz",
            },
            headers=headers,
        )
        job = await wait_job(client, generated.json()["job"]["id"])
        quiz = (await client.get(f"/api/v1/quiz-sessions/{job['quiz_session_id']}")).json()
        question = quiz["questions"][0]
        scene = {
            "page_type": "practice",
            "quiz_session_id": quiz["id"],
            "question_id": question["id"],
        }
        for number in range(2):
            accepted = await client.post(
                f"/api/v1/conversations/{conversation['id']}/messages",
                json={
                    "message": "请讲解这道题",
                    "scene": scene,
                    "idempotency_key": f"feedback-question-{number}",
                },
                headers=headers,
            )
            assert accepted.status_code == 202, accepted.text
            assert (
                await teaching_worker.execute_run(
                    settings, app.state.gateway, accepted.json()["run"]["id"]
                )
                == "SUCCEEDED"
            )
            assert ("private-feedback-marker-0" in captured[-1]) == bool(number)
            assert "private-feedback-marker-1" not in captured[-1]
            if number == 0:
                answer = (
                    question["options"][0]["key"] if question["type"] == "SINGLE_CHOICE" else True
                )
                scored = await client.post(
                    f"/api/v1/quiz-sessions/{quiz['id']}/questions/{question['id']}/answers",
                    json={"answer": answer, "idempotency_key": "feedback-answer-1"},
                    headers=headers,
                )
                assert scored.status_code == 200, scored.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,grade",
    [(Stage.PRIMARY_LOWER, 2), (Stage.PRIMARY_UPPER, 5), (Stage.JUNIOR, 7), (Stage.SENIOR, 10)],
)
@pytest.mark.parametrize("count", [1, 3, 5, 6, 10, 20])
async def test_companion_counts_and_answer_isolation(
    content_session, test_settings, stage, grade, count
):
    await create_synthetic_user(
        test_settings,
        username="companion.quiz",
        password="synthetic-pass-1",
        stage=stage.value,
        grade=grade,
    )
    app = create_app(
        test_settings.model_copy(update={"gateway_mode": "fixture", "assessment_autorun": True})
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "companion.quiz", "synthetic-pass-1")
        headers = await csrf_headers(client)
        conversation = (await client.post("/api/v1/conversations", json={}, headers=headers)).json()
        body = {
            "conversation_id": conversation["id"],
            "student_request": f"请围绕数据分类生成 {count} 道题",
            "knowledge_point": "数据分类",
            "ordinary_question_count": count,
            "idempotency_key": "companion-count-case",
        }
        response = await client.post("/api/v1/quiz-generation-jobs", json=body, headers=headers)
        assert response.status_code == 202, response.text
        job = await wait_job(client, response.json()["job"]["id"])
        assert job["status"] == "SUCCEEDED", job
        assert job["request_summary"]["generated_count"] == count
        assert "validated_batches" not in job["request_config"]
        assert "correct_answer" not in str(job)
        quiz = (await client.get(f"/api/v1/quiz-sessions/{job['quiz_session_id']}")).json()
        assert quiz["question_count"] == len(quiz["questions"]) == count
        assert len({q["stem"] for q in quiz["questions"]}) == count
        assert all("feedback" not in q and "correct_answer" not in q for q in quiz["questions"])
        again = await client.post("/api/v1/quiz-generation-jobs", json=body, headers=headers)
        assert again.json()["job"]["id"] == job["id"]
        assert (await client.get("/api/v1/quiz-options/conversation")).json()[
            "max_question_count"
        ] == 20
        for bad in [0, 21, 1.5, True]:
            invalid = await client.post(
                "/api/v1/quiz-generation-jobs",
                json={**body, "ordinary_question_count": bad},
                headers=headers,
            )
            assert invalid.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unavailable", "duplicate"])
async def test_retry_keeps_successful_batch(content_session, test_settings, failure):
    await create_synthetic_user(
        test_settings,
        username="companion.retry",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=7,
    )
    app = create_app(
        test_settings.model_copy(update={"gateway_mode": "fixture", "assessment_autorun": True})
    )
    original = app.state.gateway.invoke
    calls = []
    first_stem = None

    async def fail_second(operation, payload, **options):
        nonlocal first_stem
        calls.append(payload["request_id"])
        if len(calls) == 2 and failure == "unavailable":
            raise RuntimeError("temporary upstream failure")
        result = await original(operation, payload, **options)
        if len(calls) == 1:
            first_stem = result.output["questions"][0]["stem"]
        elif len(calls) == 2:
            import copy

            output = copy.deepcopy(result.output)
            output["questions"][0]["stem"] = "第6题：" + first_stem
            result = result.model_copy(update={"output": output})
        return result

    app.state.gateway.invoke = fail_second
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "companion.retry", "synthetic-pass-1")
        headers = await csrf_headers(client)
        conversation = (await client.post("/api/v1/conversations", json={}, headers=headers)).json()
        response = await client.post(
            "/api/v1/quiz-generation-jobs",
            json={
                "conversation_id": conversation["id"],
                "student_request": "围绕数据分类生成 10 题",
                "knowledge_point": "数据分类",
                "ordinary_question_count": 10,
                "idempotency_key": "retry-companion-batches",
            },
            headers=headers,
        )
        job = await wait_job(client, response.json()["job"]["id"])
        assert job["status"] == ("FAILED" if failure == "unavailable" else "REJECTED")
        if failure == "duplicate":
            assert job["error_code"] == "DUPLICATE_QUESTION"
        assert job["request_summary"]["generated_count"] == 5
        assert job["quiz_session_id"] is None
        assert (
            await client.post(f"/api/v1/quiz-generation-jobs/{job['id']}/retry", headers=headers)
        ).status_code == 200
        done = await wait_job(client, job["id"])
        assert done["status"] == "SUCCEEDED", done
        assert len(calls) == 3
        assert calls[1] == calls[2]
        assert calls[0] != calls[2]


@pytest.mark.asyncio
async def test_chapter_context_and_twenty_question_group(content_session, test_settings):
    from sqlalchemy import select

    from app.jobs import teaching_worker
    from app.modules.teaching.models import LessonSession
    from tests.teaching_helpers import prepare_fixture_course, teaching_settings

    revision = await prepare_fixture_course(content_session)
    settings = teaching_settings(test_settings, assessment_autorun=True)
    owner = await create_synthetic_user(
        settings,
        username="chapter.companion",
        password="synthetic-pass-1",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "chapter.companion", "synthetic-pass-1")
        headers = await csrf_headers(client)
        conversation = (await client.post("/api/v1/conversations", json={}, headers=headers)).json()
        scene = {
            "page_type": "chapter_reader",
            "chapter_id": str(revision.chapter_id),
            "chapter_revision": revision.revision,
        }
        response = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={
                "message": "解释本章的分类思路",
                "idempotency_key": "chapter-scene-question",
                "scene": scene,
            },
            headers=headers,
        )
        assert response.status_code == 202, response.text
        run = response.json()["run"]
        assert (
            await teaching_worker.execute_run(settings, app.state.gateway, run["id"]) == "SUCCEEDED"
        )
        history = (await client.get(f"/api/v1/conversations/{conversation['id']}")).json()
        assert history["messages"][-1]["source_label"].endswith(f"第 {revision.revision} 版")
        stored = await content_session.scalar(
            select(LessonSession).where(LessonSession.owner_user_id == owner.id)
        )
        assert stored.conversation_type == "FREE" and stored.chapter_id is None
        generated = await client.post(
            "/api/v1/quiz-generation-jobs",
            json={
                "conversation_id": conversation["id"],
                "student_request": "给本章出20道题",
                "scene": scene,
                "ordinary_question_count": 20,
                "idempotency_key": "chapter-twenty-questions",
            },
            headers=headers,
        )
        assert generated.status_code == 202, generated.text
        job = await wait_job(client, generated.json()["job"]["id"])
        assert job["status"] == "SUCCEEDED", job
        quiz = (await client.get(f"/api/v1/quiz-sessions/{job['quiz_session_id']}")).json()
        assert quiz["chapter_id"] == str(revision.chapter_id)
        assert quiz["source_conversation_id"] == conversation["id"]
        assert quiz["question_count"] == 20
        wrong = {**scene, "chapter_revision": revision.revision + 1}
        invalid = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={
                "message": "解释本章",
                "idempotency_key": "invalid-source-version",
                "scene": wrong,
            },
            headers=headers,
        )
        assert invalid.status_code == 409
