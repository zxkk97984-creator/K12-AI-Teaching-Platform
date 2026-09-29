from __future__ import annotations

import pytest

from app.modules.codelab.importer import import_catalog
from tests.identity_helpers import auth_headers, create_synthetic_user, login


async def _login(client, settings, username: str, stage: str = "JUNIOR") -> str:
    await create_synthetic_user(
        settings,
        username=username,
        password="synthetic-pass-1",
        stage=stage,
        grade=11 if stage == "SENIOR" else 8,
    )
    response = await login(client, username, "synthetic-pass-1")
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


@pytest.mark.asyncio
async def test_task_listing_draft_save_and_owner_scoped_draft(
    content_session, client, test_settings
) -> None:
    await import_catalog(content_session)
    owner_csrf = await _login(client, test_settings, "codelab.owner")
    tasks = await client.get("/api/v1/code-tasks")
    assert tasks.status_code == 200
    assert {item["task_id"] for item in tasks.json()["items"]} == {
        "temperature-converter",
        "list-summary",
        "odd-even",
        "even-sum",
        "palindrome-check",
        "word-frequency",
    }
    assert (await client.get("/api/v1/code-tasks/binary-search?revision=1")).status_code == 404
    runner = await client.get("/api/v1/code-runner/status")
    assert runner.status_code == 200
    if not test_settings.codelab_runner_url:
        assert runner.json()["available"] is False
    task = await client.get("/api/v1/code-tasks/temperature-converter?revision=1")
    assert task.status_code == 200
    starter = task.json()["starter_code"]
    saved = await client.put(
        "/api/v1/code-tasks/temperature-converter/draft",
        json={
            "task_revision": 1,
            "code": "def celsius_to_fahrenheit(celsius):\n    return 42\n",
        },
        headers=auth_headers(owner_csrf),
    )
    assert saved.status_code == 200
    assert saved.json()["code"] != starter
    own = await client.get("/api/v1/code-tasks/temperature-converter/draft?revision=1")
    assert own.json()["code"] == saved.json()["code"]
    revised = await client.put(
        "/api/v1/code-tasks/temperature-converter/draft",
        json={
            "task_revision": 1,
            "code": "def celsius_to_fahrenheit(celsius):\n    return celsius * 9 / 5 + 32\n",
            "base_revision": saved.json()["revision_number"],
        },
        headers=auth_headers(owner_csrf),
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["revision_number"] == saved.json()["revision_number"] + 1
    assert (await client.get("/api/v1/code-tasks/temperature-converter/draft?revision=1")).json()[
        "code"
    ] == revised.json()["code"]

    await client.post("/api/v1/auth/logout", headers=auth_headers(owner_csrf))
    other_csrf = await _login(client, test_settings, "codelab.other")
    other = await client.get("/api/v1/code-tasks/temperature-converter/draft?revision=1")
    assert other.status_code == 200
    assert other.json()["code"] == starter
    assert other.json()["code"] != saved.json()["code"]
    await client.post("/api/v1/auth/logout", headers=auth_headers(other_csrf))

    senior_csrf = await _login(client, test_settings, "codelab.senior", "SENIOR")
    senior_tasks = (await client.get("/api/v1/code-tasks")).json()["items"]
    assert {item["task_id"] for item in senior_tasks} == {
        "binary-search",
        "prediction-accuracy",
        "sort-unique",
        "balanced-brackets",
        "range-sum",
        "climbing-stairs",
    }
    assert (
        await client.get("/api/v1/code-tasks/temperature-converter?revision=1")
    ).status_code == 404
    assert (
        await client.get("/api/v1/code-tasks/temperature-converter/draft?revision=1")
    ).status_code == 404
    await client.post("/api/v1/auth/logout", headers=auth_headers(senior_csrf))


@pytest.mark.asyncio
async def test_run_unavailable_is_honest_and_idempotent(
    content_session, client, test_settings
) -> None:
    await import_catalog(content_session)
    csrf_token = await _login(client, test_settings, "codelab.run")
    headers = auth_headers(csrf_token)
    body = {
        "task_revision": 1,
        "code": "def celsius_to_fahrenheit(celsius):\n    return 32\n",
        "idempotency_key": "codelab-run-key",
    }
    first = await client.post(
        "/api/v1/code-runs?task_id=temperature-converter", json=body, headers=headers
    )
    assert first.status_code == 200, first.text
    first_run = first.json()["run"]
    if test_settings.codelab_runner_url:
        assert first_run["status"] in {"SUCCEEDED", "FAILED", "TIMEOUT", "OUTPUT_LIMIT"}
        assert first_run["result"]["grading"]["status"] in {"PARTIAL", "FAILED", "PASSED"}
    else:
        assert first_run["status"] == "UNAVAILABLE"
        assert first_run["deterministic_score"] is None
    replay = await client.post(
        "/api/v1/code-runs?task_id=temperature-converter", json=body, headers=headers
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["run"]["id"] == first_run["id"]
    conflict = await client.post(
        "/api/v1/code-runs?task_id=temperature-converter",
        json={**body, "code": "def celsius_to_fahrenheit(celsius):\n    return 0\n"},
        headers=headers,
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_catalog_filters_favorites_and_history_are_owner_scoped(
    content_session, client, test_settings
) -> None:
    await import_catalog(content_session)
    csrf_token = await _login(client, test_settings, "codelab.catalog")
    headers = auth_headers(csrf_token)

    filtered = await client.get(
        "/api/v1/code-tasks",
        params={"q": "奇偶", "category": "PYTHON_BASICS", "difficulty": "EASY", "limit": 2},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    task = filtered.json()["items"][0]
    assert task["task_id"] == "odd-even"
    assert task["progress"]["status"] == "NOT_STARTED"
    assert task["course_link"] is None

    assert (
        await client.put("/api/v1/code-tasks/odd-even/favorite", json={}, headers=headers)
    ).status_code == 200
    assert (
        await client.put("/api/v1/code-tasks/odd-even/favorite", json={}, headers=headers)
    ).status_code == 200
    favorites = await client.get("/api/v1/code-tasks", params={"favorite_only": True})
    assert [item["task_id"] for item in favorites.json()["items"]] == ["odd-even"]

    run = await client.post(
        "/api/v1/code-runs?task_id=odd-even",
        json={
            "task_revision": 1,
            "code": "def is_even(number):\n    return number % 2 == 0\n",
            "idempotency_key": "catalog-history-run",
            "purpose": "EXAMPLE",
        },
        headers=headers,
    )
    assert run.status_code == 200
    history = await client.get("/api/v1/code-runs", params={"purpose": "EXAMPLE", "limit": 1})
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["source_label"] == "独立题库"

    await client.post("/api/v1/auth/logout", headers=headers)
    other_csrf = await _login(client, test_settings, "codelab.catalog.other")
    other_favorites = await client.get("/api/v1/code-tasks", params={"favorite_only": True})
    assert other_favorites.json()["items"] == []
    assert (await client.get("/api/v1/code-runs")).json()["items"] == []
    assert (
        await client.delete(
            "/api/v1/code-tasks/odd-even/favorite", headers=auth_headers(other_csrf)
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_real_runner_bridge_returns_trusted_grade(
    content_session, client, test_settings
) -> None:
    if not test_settings.codelab_runner_url:
        pytest.skip("real runner bridge requires CODELAB_RUNNER_URL")
    await import_catalog(content_session)
    csrf_token = await _login(client, test_settings, "codelab.real")
    response = await client.post(
        "/api/v1/code-runs?task_id=temperature-converter",
        json={
            "task_revision": 1,
            "code": ("def celsius_to_fahrenheit(celsius):\n    return celsius * 9 / 5 + 32\n"),
            "idempotency_key": "codelab-real-correct",
        },
        headers=auth_headers(csrf_token),
    )
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    assert run["status"] == "SUCCEEDED"
    assert run["correctness_status"] == "PASSED"
    assert run["deterministic_score"] == 70
