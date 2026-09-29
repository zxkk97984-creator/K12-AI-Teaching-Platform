from __future__ import annotations

import pytest

from app.jobs.worker import run_once


@pytest.mark.asyncio
async def test_worker_one_shot_recovers_and_consumes_no_phantom_jobs(test_settings) -> None:
    result = await run_once(test_settings)
    assert set(result) == {
        "recovered_teaching",
        "recovered_authoring",
        "recovered_codelab",
        "recovered_assessment",
        "teaching_processed",
        "authoring_processed",
        "codelab_processed",
        "assessment_processed",
    }
    assert result["teaching_processed"] == 0
    assert result["authoring_processed"] == 0
    assert result["codelab_processed"] == 0
    assert result["assessment_processed"] == 0
