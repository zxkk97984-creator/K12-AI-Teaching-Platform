"""Account-owned reading position for the two built-in picturebooks."""

from __future__ import annotations

import pytest

from tests.identity_helpers import create_synthetic_user
from tests.teaching_helpers import create_app_client, csrf_headers, login, teaching_settings

PASSWORD = "synthetic-pass-1"


@pytest.mark.asyncio
async def test_picturebook_progress_survives_reload_and_is_owner_scoped(test_settings):
    settings = teaching_settings(test_settings)
    for username in ("picturebook.owner", "picturebook.other"):
        await create_synthetic_user(
            settings,
            username=username,
            password=PASSWORD,
            stage="PRIMARY_LOWER",
            grade=2,
        )
    crow = "/api/v1/learning/picturebooks/crow/progress"
    tortoise = "/api/v1/learning/picturebooks/tortoise/progress"

    async with create_app_client(settings) as client:
        assert (await client.get(crow)).status_code == 401
        assert (await login(client, "picturebook.owner", PASSWORD)).status_code == 200
        empty = await client.get(crow)
        assert empty.status_code == 200
        assert empty.json() == {"story_id": "crow", "page_index": 0, "updated_at": None}
        assert (await client.get(tortoise)).json()["page_index"] == 0

        headers = await csrf_headers(client)
        saved = await client.put(crow, json={"page_index": 2}, headers=headers)
        assert saved.status_code == 200, saved.text
        assert saved.json()["story_id"] == "crow"
        assert saved.json()["page_index"] == 2
        assert saved.json()["updated_at"] is not None
        assert (await client.get(crow)).json()["page_index"] == 2
        assert (await client.get(tortoise)).json()["page_index"] == 0

    async with create_app_client(settings) as client:
        assert (await login(client, "picturebook.owner", PASSWORD)).status_code == 200
        assert (await client.get(crow)).json()["page_index"] == 2

        assert (await login(client, "picturebook.other", PASSWORD)).status_code == 200
        assert (await client.get(crow)).json()["page_index"] == 0
        other_saved = await client.put(
            crow, json={"page_index": 1}, headers=await csrf_headers(client)
        )
        assert other_saved.status_code == 200
        assert (await client.get(crow)).json()["page_index"] == 1

        assert (await login(client, "picturebook.owner", PASSWORD)).status_code == 200
        assert (await client.get(crow)).json()["page_index"] == 2


@pytest.mark.asyncio
async def test_picturebook_progress_rejects_unknown_story_invalid_page_and_csrf(test_settings):
    settings = teaching_settings(test_settings)
    await create_synthetic_user(
        settings,
        username="picturebook.validation",
        password=PASSWORD,
        stage="PRIMARY_LOWER",
        grade=2,
    )
    crow = "/api/v1/learning/picturebooks/crow/progress"
    async with create_app_client(settings) as client:
        assert (await login(client, "picturebook.validation", PASSWORD)).status_code == 200
        headers = await csrf_headers(client)
        assert (
            await client.get("/api/v1/learning/picturebooks/unknown/progress")
        ).status_code == 404
        assert (
            await client.put(
                "/api/v1/learning/picturebooks/unknown/progress",
                json={"page_index": 1},
                headers=headers,
            )
        ).status_code == 404
        assert (await client.put(crow, json={"page_index": 1})).status_code == 403
        for invalid in (-1, 3, True, 1.0, "1"):
            response = await client.put(crow, json={"page_index": invalid}, headers=headers)
            assert response.status_code == 422, response.text
        assert (
            await client.put(crow, json={"page_index": 1, "score": 100}, headers=headers)
        ).status_code == 422
        assert (await client.get(crow)).json()["updated_at"] is None
