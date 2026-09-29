"""Account-scoped nickname and private avatar API."""

from __future__ import annotations

import io

import pytest
from PIL import Image, PngImagePlugin

from tests.identity_helpers import auth_headers, create_synthetic_user, login


def _png_with_metadata() -> bytes:
    image = Image.new("RGBA", (640, 480), "#d9bd7e")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private-note", "must-not-be-served")
    output = io.BytesIO()
    image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


@pytest.mark.asyncio
async def test_student_nickname_is_saved_without_changing_login_or_grade(client, test_settings):
    await create_synthetic_user(
        test_settings,
        username="avatar.nickname",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=8,
    )
    signed_in = await login(client, "avatar.nickname", "synthetic-pass-1")
    assert signed_in.status_code == 200
    before = signed_in.json()
    updated = await client.patch(
        "/api/v1/me/profile",
        json={"base_revision": before["profile"]["revision"], "nickname": "  小 星  "},
        headers=auth_headers(before["csrf_token"]),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["profile"]["nickname"] == "小 星"
    assert updated.json()["profile"]["stage"] == "JUNIOR"
    assert updated.json()["profile"]["grade"] == 8
    assert updated.json()["user"]["username"] == "avatar.nickname"
    assert (await client.get("/api/v1/me")).json()["profile"]["nickname"] == "小 星"

    rejected = await client.patch(
        "/api/v1/me/profile",
        json={"base_revision": updated.json()["profile"]["revision"], "nickname": "欺骗\u202e文本"},
        headers=auth_headers(before["csrf_token"]),
    )
    assert rejected.status_code == 422
    assert (await client.get("/api/v1/me")).json()["profile"]["nickname"] == "小 星"


@pytest.mark.asyncio
async def test_avatar_upload_is_normalized_owner_scoped_and_removable(client, test_settings):
    await create_synthetic_user(
        test_settings,
        username="avatar.owner",
        password="synthetic-pass-1",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    await create_synthetic_user(
        test_settings,
        username="avatar.other",
        password="synthetic-pass-2",
        stage="PRIMARY_UPPER",
        grade=4,
    )
    owner = await login(client, "avatar.owner", "synthetic-pass-1")
    assert owner.status_code == 200
    token = owner.json()["csrf_token"]
    image = _png_with_metadata()
    missing_csrf = await client.put(
        "/api/v1/me/avatar", content=image, headers={"Content-Type": "image/png"}
    )
    assert missing_csrf.status_code == 403
    uploaded = await client.put(
        "/api/v1/me/avatar",
        content=image,
        headers={**auth_headers(token), "Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200, uploaded.text
    profile = uploaded.json()["profile"]
    assert profile["avatar_url"].startswith("/api/v1/me/avatar?v=")
    assert profile["revision"] == owner.json()["profile"]["revision"] + 1
    avatar = await client.get(profile["avatar_url"])
    assert avatar.status_code == 200
    assert avatar.headers["content-type"] == "image/png"
    assert "no-store" in avatar.headers["cache-control"]
    assert avatar.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(avatar.content)) as normalized:
        assert normalized.size == (256, 256)
        assert "private-note" not in normalized.info
    replay = await client.put(
        "/api/v1/me/avatar",
        content=image,
        headers={**auth_headers(token), "Content-Type": "image/png"},
    )
    assert replay.status_code == 200
    assert replay.json()["profile"]["revision"] == profile["revision"]

    wrong_type = await client.put(
        "/api/v1/me/avatar",
        content=b"<svg></svg>",
        headers={**auth_headers(token), "Content-Type": "image/svg+xml"},
    )
    assert wrong_type.status_code == 415
    broken = await client.put(
        "/api/v1/me/avatar",
        content=b"not a png",
        headers={**auth_headers(token), "Content-Type": "image/png"},
    )
    assert broken.status_code == 422
    too_large = await client.put(
        "/api/v1/me/avatar",
        content=b"x" * (2 * 1024 * 1024 + 1),
        headers={**auth_headers(token), "Content-Type": "image/png"},
    )
    assert too_large.status_code == 413

    other = await login(client, "avatar.other", "synthetic-pass-2")
    assert other.status_code == 200
    assert (await client.get(profile["avatar_url"])).status_code == 404
    assert (await client.get("/api/v1/me/avatar?user_id=avatar.owner")).status_code == 404
    assert (
        await client.delete("/api/v1/me/avatar", headers=auth_headers(other.json()["csrf_token"]))
    ).json()["profile"]["avatar_url"] is None

    owner_again = await login(client, "avatar.owner", "synthetic-pass-1")
    assert owner_again.status_code == 200
    removed = await client.delete(
        "/api/v1/me/avatar", headers=auth_headers(owner_again.json()["csrf_token"])
    )
    assert removed.status_code == 200
    assert removed.json()["profile"]["avatar_url"] is None
    assert (await client.get("/api/v1/me/avatar")).status_code == 404
