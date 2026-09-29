from __future__ import annotations

import asyncio
import threading

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import get_engine
from app.jobs import codelab_worker
from app.modules.codelab.importer import import_catalog
from app.modules.codelab.models import CodeRun
from app.modules.codelab.trusted import expected_output
from tests.identity_helpers import create_synthetic_user


async def test_example_worker_executes_public_examples_without_grading(
    content_session, test_settings, monkeypatch
) -> None:
    await import_catalog(content_session)
    user = await create_synthetic_user(
        test_settings,
        username="codelab.worker.example",
        password="synthetic-worker-pass",
        stage="JUNIOR",
        grade=8,
    )
    factory = async_sessionmaker(
        get_engine(test_settings.active_database_url, "test"), expire_on_commit=False
    )
    async with factory() as db:
        run = CodeRun(
            owner_user_id=user.id,
            task_id="odd-even",
            task_revision=1,
            scope_key="standalone",
            purpose="EXAMPLE",
            idempotency_key="worker-example-run",
            code="def is_even(number):\n    return number % 2 == 0\n",
            code_sha256="0" * 64,
            status="QUEUED",
            execution_status="QUEUED",
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    observed_cases: list[str] = []

    def fake_request(_settings, payload: dict) -> dict:
        observed_cases.append(payload["case_id"])
        return {
            "case_id": payload["case_id"],
            "execution_status": "COMPLETED",
            "actual_output": expected_output(payload["task_id"], payload["input"]),
            "student_stdout": "",
            "student_stderr": "",
        }

    monkeypatch.setattr(codelab_worker, "_request", fake_request)
    assert await codelab_worker.execute_code_run(test_settings, run_id) == "SUCCEEDED"

    async with factory() as db:
        saved = await db.scalar(select(CodeRun).where(CodeRun.id == run_id))
        assert saved is not None
        assert saved.correctness_status == "NOT_VERIFIED"
        assert saved.deterministic_score is None
        assert saved.result is not None
        assert "grading" not in saved.result
        assert [item["case_id"] for item in saved.result["observations"]] == [
            "example-1",
            "example-2",
            "example-3",
        ]
    assert observed_cases == ["example-1", "example-2", "example-3"]


def test_runner_system_errors_are_not_reported_as_success() -> None:
    assert codelab_worker._execution([{"execution_status": "RUNNER_ERROR"}]) == "SYSTEM_ERROR"
    assert codelab_worker._execution([{"execution_status": "UNKNOWN"}]) == "SYSTEM_ERROR"


async def test_cancelled_run_stops_after_the_in_flight_case(
    content_session, test_settings, monkeypatch
) -> None:
    await import_catalog(content_session)
    user = await create_synthetic_user(
        test_settings,
        username="codelab.worker.cancel",
        password="synthetic-worker-pass",
        stage="JUNIOR",
        grade=8,
    )
    factory = async_sessionmaker(
        get_engine(test_settings.active_database_url, "test"), expire_on_commit=False
    )
    async with factory() as db:
        run = CodeRun(
            owner_user_id=user.id,
            task_id="odd-even",
            task_revision=1,
            scope_key="standalone",
            purpose="GRADE",
            idempotency_key="worker-cancel-run",
            code="def is_even(number):\n    return number % 2 == 0\n",
            code_sha256="0" * 64,
            status="QUEUED",
            execution_status="QUEUED",
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    started = threading.Event()
    release = threading.Event()
    observed_cases: list[str] = []

    def delayed_request(_settings, payload: dict) -> dict:
        observed_cases.append(payload["case_id"])
        started.set()
        release.wait(timeout=5)
        return {
            "case_id": payload["case_id"],
            "execution_status": "COMPLETED",
            "actual_output": expected_output(payload["task_id"], payload["input"]),
            "student_stdout": "",
            "student_stderr": "",
        }

    monkeypatch.setattr(codelab_worker, "_request", delayed_request)
    execution = asyncio.create_task(codelab_worker.execute_code_run(test_settings, run_id))
    assert await asyncio.to_thread(started.wait, 3)
    try:
        async with factory() as db:
            saved = await db.scalar(select(CodeRun).where(CodeRun.id == run_id))
            assert saved is not None
            saved.status = "CANCELLED"
            saved.execution_status = "CANCELLED"
            await db.commit()
    finally:
        release.set()

    assert await asyncio.wait_for(execution, timeout=5) == "CANCELLED"
    assert observed_cases == ["f1-1"]
    async with factory() as db:
        saved = await db.scalar(select(CodeRun).where(CodeRun.id == run_id))
        assert saved is not None
        assert saved.status == "CANCELLED"
        assert saved.correctness_status == "NOT_VERIFIED"
        assert saved.deterministic_score is None
