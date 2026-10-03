"""Opt-in real Tutor/Designer acceptance; all records stay in the isolated DB."""

import json
import os
from pathlib import Path

import httpx
import pytest

from app.jobs import teaching_worker
from app.main import create_app
from app.modules.ai.models import AIConfiguration
from app.modules.ai.schemas import RegistryData
from app.modules.assessment.service import execute_student_generation
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import csrf_headers, teaching_settings


@pytest.mark.skipif(
    os.environ.get("K12_COMPANION_LIVE") != "1", reason="Explicit live acceptance required"
)
@pytest.mark.parametrize(
    "stage,grade", [("PRIMARY_LOWER", 2), ("PRIMARY_UPPER", 5), ("JUNIOR", 8), ("SENIOR", 11)]
)
@pytest.mark.asyncio
async def test_real_companion_reply_and_six_questions(test_settings, content_session, stage, grade):
    snapshot = json.loads(Path(os.environ["K12_AI_REGISTRY_SNAPSHOT"]).read_text())
    RegistryData.model_validate(snapshot["data"])
    content_session.add(AIConfiguration(id=1, revision=snapshot["revision"], data=snapshot["data"]))
    await content_session.commit()
    settings = teaching_settings(
        test_settings,
        gateway_mode="knodo",
        gateway_timeout_seconds=120,
        teaching_lease_seconds=600,
        assessment_autorun=False,
    )
    await create_synthetic_user(
        settings,
        username="live.companion",
        password="synthetic-live-pass-1",
        stage=stage,
        grade=grade,
    )
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:15173"
    ) as client:
        await login(client, "live.companion", "synthetic-live-pass-1")
        headers = await csrf_headers(client)
        conversation = (await client.post("/api/v1/conversations", json={}, headers=headers)).json()
        question = "请用水果的例子解释数据分类，以及颜色为什么可以作为分类特征。"
        response = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"message": question, "idempotency_key": "live-companion-explain"},
            headers=headers,
        )
        assert response.status_code == 202, response.text
        run = response.json()["run"]
        status = await teaching_worker.execute_run(settings, app.state.gateway, run["id"])
        stored = (await client.get(f"/api/v1/agent-runs/{run['id']}")).json()
        assert status == "SUCCEEDED", (
            status,
            stored.get("error_category"),
            stored.get("stale_reason"),
        )
        assert stored["fixture"] is False
        response = await client.post(
            "/api/v1/quiz-generation-jobs",
            json={
                "conversation_id": conversation["id"],
                "student_request": "请围绕数据分类生成6道题",
                "knowledge_point": "数据分类",
                "ordinary_question_count": 6,
                "difficulty": "EASY",
                "idempotency_key": "live-companion-six-questions",
            },
            headers=headers,
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job"]["id"]
        status = await execute_student_generation(settings, app.state.gateway, job_id)
        job = (await client.get(f"/api/v1/quiz-generation-jobs/{job_id}")).json()["job"]
        assert status == "SUCCEEDED", (status, job.get("error_code"), job.get("error_detail"))
        assert job["fixture"] is False
        assert job["request_summary"]["generated_count"] == 6
        assert "validated_batches" not in job["request_config"]
        quiz = (await client.get(f"/api/v1/quiz-sessions/{job['quiz_session_id']}")).json()
        assert quiz["question_count"] == len(quiz["questions"]) == 6
        assert all("feedback" not in entry for entry in quiz["questions"])
