"""A saved Tutor reply is a durable, owner-scoped Designer source."""

import asyncio
import uuid

import pytest

from app.jobs import teaching_worker
from app.modules.assessment.service import execute_student_generation
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import create_app_client, csrf_headers, teaching_settings


@pytest.mark.asyncio
async def test_conversation_to_quiz_is_durable_and_answer_free(test_settings):
    settings = teaching_settings(test_settings)
    await create_synthetic_user(
        settings,
        username="conversation.quiz.a",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=7,
    )
    await create_synthetic_user(
        settings,
        username="conversation.quiz.b",
        password="synthetic-pass-2",
        stage="JUNIOR",
        grade=7,
    )
    client = create_app_client(settings)
    async with client:
        await login(client, "conversation.quiz.a", "synthetic-pass-1")
        opened = await client.post(
            "/api/v1/conversations", json={}, headers=await csrf_headers(client)
        )
        assert opened.status_code == 201, opened.text
        conversation_id = opened.json()["id"]
        asked = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": "请解释食物链与生态关系", "idempotency_key": "quiz-source-turn-1"},
            headers=await csrf_headers(client),
        )
        assert asked.status_code == 202, asked.text
        assert (
            await teaching_worker.execute_run(
                settings, client._transport.app.state.gateway, asked.json()["run"]["id"]
            )
            == "SUCCEEDED"
        )
        detail = (await client.get(f"/api/v1/conversations/{conversation_id}")).json()
        message_id = detail["messages"][-1]["id"]
        request = {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "knowledge_point": "食物链与生态关系",
            "ordinary_question_count": 1,
            "idempotency_key": f"student-quiz-{uuid.uuid4()}",
        }
        created = await client.post(
            "/api/v1/quiz-generation-jobs", json=request, headers=await csrf_headers(client)
        )
        assert created.status_code == 202, created.text
        job_id = created.json()["job"]["id"]
        repeated = await client.post(
            "/api/v1/quiz-generation-jobs", json=request, headers=await csrf_headers(client)
        )
        assert repeated.status_code == 202
        assert repeated.json()["job"]["id"] == job_id
        job = (await client.get(f"/api/v1/quiz-generation-jobs/{job_id}")).json()["job"]
        if job["status"] == "QUEUED":
            await execute_student_generation(
                settings, client._transport.app.state.gateway, uuid.UUID(job_id)
            )
        for _ in range(30):
            job = (await client.get(f"/api/v1/quiz-generation-jobs/{job_id}")).json()["job"]
            if job["status"] not in {"QUEUED", "RUNNING"}:
                break
            await asyncio.sleep(0.1)
        assert job["status"] == "SUCCEEDED", job
        assert job["source_conversation_id"] == conversation_id
        assert job["source_message_id"] == message_id
        quiz_id = job["quiz_session_id"]
        assert quiz_id
        quiz = (await client.get(f"/api/v1/quiz-sessions/{quiz_id}")).json()
        assert quiz["source_conversation_id"] == conversation_id
        assert quiz["chapter_id"] is None
        assert quiz["questions"]
        assert "correct_answer" not in quiz["questions"][0]
        assert "explanation" not in quiz["questions"][0]
        jobs = (
            await client.get(f"/api/v1/quiz-generation-jobs?conversation_id={conversation_id}")
        ).json()["items"]
        assert jobs[0]["quiz_session_id"] == quiz_id
        await login(client, "conversation.quiz.b", "synthetic-pass-2")
        assert (await client.get(f"/api/v1/quiz-generation-jobs/{job_id}")).status_code == 404
        assert (await client.get(f"/api/v1/quiz-sessions/{quiz_id}")).status_code == 404
