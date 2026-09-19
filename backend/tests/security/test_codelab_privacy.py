from __future__ import annotations

import json

import pytest

from app.modules.codelab.importer import import_catalog
from tests.identity_helpers import auth_headers, create_synthetic_user, login


async def _login(client, settings, username: str) -> str:
    await create_synthetic_user(
        settings, username=username, password="synthetic-privacy-pass", stage="JUNIOR", grade=8
    )
    response = await login(client, username, "synthetic-privacy-pass")
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _keys(value):
    if isinstance(value, dict):
        yield from value.keys()
        for item in value.values():
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


@pytest.mark.asyncio
async def test_export_and_local_delete_are_owner_scoped_and_platform_honest(
    content_session, client, test_settings
) -> None:
    await import_catalog(content_session)
    owner_csrf = await _login(client, test_settings, "privacy.owner")
    owner_headers = auth_headers(owner_csrf)
    saved = await client.put(
        "/api/v1/code-tasks/temperature-converter/draft",
        json={"task_revision": 1, "code": "def celsius_to_fahrenheit(celsius):\n    return 99\n"},
        headers=owner_headers,
    )
    assert saved.status_code == 200
    run = await client.post(
        "/api/v1/code-runs?task_id=temperature-converter",
        json={
            "task_revision": 1,
            "code": saved.json()["code"],
            "idempotency_key": "privacy-owner-run",
        },
        headers=owner_headers,
    )
    assert run.status_code == 200
    run_id = run.json()["run"]["id"]

    export = await client.get("/api/v1/me/data-export")
    assert export.status_code == 200
    exported = export.json()
    assert exported["schema_version"] == "k12.local-data-export.v1"
    assert exported["codelab"]["drafts"][0]["code"].endswith("return 99\n")
    assert exported["codelab"]["runs"][0]["status"] in {
        "UNAVAILABLE",
        "SUCCEEDED",
        "FAILED",
        "TIMEOUT",
        "OUTPUT_LIMIT",
        "SYSTEM_ERROR",
    }
    assert exported["scope"]["platform_status"] == "NOT_CONNECTED"
    assert not {
        "password_hash",
        "token_hash",
        "session_token",
        "reference_solution",
        "hidden_tests",
    } & set(_keys(exported["codelab"]))
    assert "synthetic-runner-control-token" not in json.dumps(exported, ensure_ascii=False)

    csrf_rejected = await client.post(
        "/api/v1/me/deletion-requests",
        json={"idempotency_key": "privacy-owner-delete"},
        headers={"Origin": "http://127.0.0.1:15173"},
    )
    assert csrf_rejected.status_code == 403

    await client.post("/api/v1/auth/logout", headers=owner_headers)
    other_csrf = await _login(client, test_settings, "privacy.other")
    other_export = await client.get("/api/v1/me/data-export")
    assert other_export.status_code == 200
    assert other_export.json()["codelab"] == {"drafts": [], "runs": []}
    assert (await client.get(f"/api/v1/code-runs/{run_id}")).status_code == 404
    other_save = await client.put(
        "/api/v1/code-tasks/temperature-converter/draft",
        json={"task_revision": 1, "code": "def celsius_to_fahrenheit(celsius):\n    return 1\n"},
        headers=auth_headers(other_csrf),
    )
    assert other_save.status_code == 200
    await client.post("/api/v1/auth/logout", headers=auth_headers(other_csrf))

    owner_csrf = await _login(client, test_settings, "privacy.owner")
    owner_headers = auth_headers(owner_csrf)
    deleted = await client.post(
        "/api/v1/me/deletion-requests",
        json={"idempotency_key": "privacy-owner-delete"},
        headers=owner_headers,
    )
    assert deleted.status_code == 200
    deletion = deleted.json()
    assert deletion["idempotent_replay"] is False
    assert deletion["request"]["status"] == "LOCAL_COMPLETED"
    assert deletion["request"]["platform_status"] == "NOT_REQUESTED"
    assert deletion["request"]["scope"]["requested_scope"] == "CODELAB_ONLY"
    assert deletion["request"]["scope"]["local"] == {
        "codelab_code_drafts": 1,
        "codelab_code_runs": 1,
    }
    replay = await client.post(
        "/api/v1/me/deletion-requests",
        json={"idempotency_key": "privacy-owner-delete"},
        headers=owner_headers,
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["request"]["id"] == deletion["request"]["id"]
    assert (await client.get("/api/v1/me/data-export")).json()["codelab"] == {
        "drafts": [],
        "runs": [],
    }
    starter = (
        await client.get("/api/v1/code-tasks/temperature-converter/draft?revision=1")
    ).json()["code"]
    assert starter != "def celsius_to_fahrenheit(celsius):\n    return 99\n"
    assert (await client.get(f"/api/v1/code-runs/{run_id}")).status_code == 404
    requests = await client.get("/api/v1/me/deletion-requests")
    assert requests.status_code == 200
    assert len(requests.json()["items"]) == 1
    await client.post("/api/v1/auth/logout", headers=owner_headers)

    other_csrf = await _login(client, test_settings, "privacy.other")
    other_export = (await client.get("/api/v1/me/data-export")).json()
    assert other_export["codelab"]["drafts"][0]["code"].endswith("return 1\n")
    assert (await client.get("/api/v1/me/deletion-requests")).json()["items"] == []
    await client.post("/api/v1/auth/logout", headers=auth_headers(other_csrf))
