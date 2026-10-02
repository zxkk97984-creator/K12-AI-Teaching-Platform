"""Opt-in acceptance of lookup rounds against the configured real teachers."""

import json
import os
import uuid
from pathlib import Path

import pytest

from app.jobs import teaching_worker
from app.modules.ai.models import AIConfiguration
from app.modules.ai.schemas import RegistryData
from app.modules.assessment.models import QuizAttempt, QuizQuestion, QuizSession
from app.modules.content.importer import import_package
from app.modules.content.package import load_package
from app.modules.lookup.rounds import unwrap_final
from tests.content_helpers import REPO_ROOT
from tests.identity_helpers import create_synthetic_user, login
from tests.teaching_helpers import (
    create_app_client,
    csrf_headers,
    teaching_settings,
)


@pytest.mark.skipif(
    os.environ.get("K12_LOOKUP_LIVE_ACCEPTANCE") != "1",
    reason="Requires private teacher registry and explicit real Knodo acceptance",
)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,grade,teacher",
    [
        ("PRIMARY_LOWER", 2, "primary"),
        ("PRIMARY_UPPER", 5, "primary"),
        ("JUNIOR", 8, "junior"),
        ("SENIOR", 11, "senior"),
    ],
)
async def test_live_normal_reply_and_three_readonly_queries(
    test_settings, content_session, stage, grade, teacher
):
    source = Path(os.environ["K12_AI_REGISTRY_SNAPSHOT"])
    snapshot = json.loads(source.read_text())
    RegistryData.model_validate(snapshot["data"])
    content_session.add(AIConfiguration(id=1, revision=snapshot["revision"], data=snapshot["data"]))
    await content_session.commit()
    await import_package(
        content_session,
        load_package(REPO_ROOT / "curriculum/source/original/original-books-v1"),
        dry_run=False,
    )
    settings = teaching_settings(
        test_settings, gateway_mode="knodo", gateway_timeout_seconds=120, teaching_lease_seconds=600
    )
    assert settings.active_database_url == test_settings.active_database_url
    owner = await create_synthetic_user(
        settings,
        username="review.lookup.live",
        password="synthetic-review-live-pass",
        stage=stage,
        grade=grade,
    )
    other = await create_synthetic_user(
        settings,
        username="review.lookup.other",
        password="synthetic-review-other-pass",
        stage=stage,
        grade=grade,
    )
    # Explicit synthetic scored records prove populated queries and owner filtering.
    for user, title in [(owner, "我的合成错题记录"), (other, "OTHER_STUDENT_PRIVATE_MARKER")]:
        quiz = QuizSession(
            owner_user_id=user.id,
            source_conversation_id=uuid.uuid4(),
            source_title=title,
            curriculum_revision="live-lookup-synthetic",
            stage=stage,
            grade=grade,
            source_kind="AI_DRAFT",
            source_label="fixture",
            difficulty="EASY",
            question_count=1,
            max_attempts=3,
            max_hints=2,
            scoring_version="v1",
            thresholds_version="v1",
        )
        content_session.add(quiz)
        await content_session.flush()
        question = QuizQuestion(
            session_id=quiz.id,
            position=0,
            question_key="synthetic-live-question",
            objective_id="lookup",
            type="TRUE_FALSE",
            stem=title + "：人工智能会使用数据。",
            correct_answer=True,
            explanation="这是显式合成题，用来验证平台记录查询。",
            hints=["提示尚未领取"],
            source_refs=[],
            origin="FIXTURE",
        )
        content_session.add(question)
        await content_session.flush()
        content_session.add(
            QuizAttempt(
                owner_user_id=user.id,
                session_id=quiz.id,
                question_id=question.id,
                attempt_no=1,
                answer=False,
                outcome="INCORRECT",
                is_correct=False,
                idempotency_key=str(uuid.uuid4()),
                payload_hash="a" * 64,
                scoring_version="v1",
            )
        )
    await content_session.commit()
    async with create_app_client(settings) as client:
        assert (
            await login(client, "review.lookup.live", "synthetic-review-live-pass")
        ).status_code == 200
        gateway = client._transport.app.state.gateway
        original = gateway.invoke
        calls = []
        raw_outputs = []

        async def observe(operation, payload, **kwargs):
            result = await original(operation, payload, **kwargs)
            raw_outputs.append(result.output)
            calls.append(
                (
                    result.mode,
                    result.status.value,
                    (result.output or {}).get("kind"),
                    result.error.category.value if result.error else None,
                    result.error.reason_code if result.error else None,
                )
            )
            return result

        gateway.invoke = observe
        for message, querying in [
            (
                "本题不涉及平台课程、我的错题或学习进度，不要请求查询。请直接用一个简短的生活例子解释人工智能。",
                False,
            ),
            (
                "请查询当前学段所有平台课程资料、我本人的所有错题和学习进度。必须通过COURSE_SEARCH、WRONG_QUESTIONS、LEARNING_PROGRESS三类只读查询，不加关键词或日期筛选。查询后只做简短定性解释，不写数字、网址或卡片内容，具体记录以平台卡片为准。",
                True,
            ),
        ]:
            calls.clear()
            raw_outputs.clear()
            created = await client.post(
                "/api/v1/conversations", json={}, headers=await csrf_headers(client)
            )
            assert created.status_code == 201
            assert created.json()["teacher"]["id"] == teacher
            session_id = created.json()["id"]
            accepted = await client.post(
                f"/api/v1/conversations/{session_id}/messages",
                json={"message": message, "idempotency_key": f"live-lookup-{session_id}"},
                headers=await csrf_headers(client),
            )
            assert accepted.status_code == 202
            status = await teaching_worker.execute_run(
                settings, gateway, accepted.json()["run"]["id"]
            )
            print(
                "REAL LOOKUP stage=",
                stage,
                "querying=",
                querying,
                "status=",
                status,
                "calls=",
                calls,
                flush=True,
            )
            assert status == "SUCCEEDED"
            detail = (await client.get(f"/api/v1/conversations/{session_id}")).json()
            raw_response = unwrap_final(raw_outputs[-1])
            assert raw_response and raw_response.get("message_markdown")
            assert (
                detail["messages"][-1]["card"]["message_markdown"]
                == raw_response["message_markdown"]
            )
            cards = detail["messages"][-1].get("card", {}).get("lookup_cards", [])
            assert all(call[0] == "knodo" and call[1] == "OK" for call in calls)
            if querying:
                assert len(calls) == 2
                assert {card["tool"] for card in cards} == {
                    "COURSE_SEARCH",
                    "WRONG_QUESTIONS",
                    "LEARNING_PROGRESS",
                }
                assert all(
                    any(card["tool"] == tool and card["status"] == "OK" for card in cards)
                    for tool in ["COURSE_SEARCH", "WRONG_QUESTIONS", "LEARNING_PROGRESS"]
                )
                serialized = json.dumps(detail["messages"][-1], ensure_ascii=False)
                assert "我的合成错题记录" in serialized
                assert "OTHER_STUDENT_PRIVATE_MARKER" not in serialized
                assert "correct_answer" not in serialized and "提示尚未领取" not in serialized
                for card in cards:
                    if card.get("target"):
                        target = {
                            key: value for key, value in card["target"].items() if value is not None
                        }
                        opened = await client.get("/api/v1/learning/lookup-target", params=target)
                        assert opened.status_code == 200
                        assert opened.json()["route"] == card["route"]
                        assert opened.json()["route"].startswith("/")
            else:
                assert len(calls) == 1 and not cards
