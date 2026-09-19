"""T21 acceptance: controlled teaching animations.

A1 deterministic templates · A2 parameter boundaries · A3 registry/binding and
illegal ids/params · A5 no executable payload · A6 unpublished and out-of-stage
animations are filtered server-side (reusing the frozen content truth).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.main import create_app
from app.modules.content.importer import import_package
from app.modules.content.models import ContentProfile, ReviewStatus
from app.modules.content.package import load_package
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import (
    publish_revision,
    record_review,
    withdraw_revision,
)
from app.modules.identity.models import Stage, UserRole
from app.modules.resources.animation_service import (
    DEFINITIONS_PATH,
    AnimationNotVisible,
    AnimationParamsRejected,
    animation_spec,
    load_definitions,
    load_visible_animation,
    public_definition,
    validate_params,
    visible_animations,
)
from app.modules.teaching.context import build_session_context
from app.modules.teaching.models import LessonSession
from app.modules.teaching.service import create_session
from tests.content_helpers import FIXTURE_PACKAGE, LEGACY_PACKAGE, revision_by_slug
from tests.identity_helpers import (
    ORIGIN,
    auth_headers,
    create_synthetic_user,
    csrf,
    login,
)

SENIOR_COURSE, SENIOR_CHAPTER = "algorithm-everyday", "ch03"
SENIOR_ANIMATION = "anim-sort-bubble-v1"
SEARCH_ANIMATION = "anim-binary-search-v1"
DRAFT_ANIMATION = "anim-sort-bubble-draft-v1"
FIXTURE_ANIMATION = "anim-binary-search-fixture-v1"
PASSWORD = "synthetic-T21-Pass-1234"


@pytest_asyncio.fixture
async def aclient(test_settings: Settings, tmp_path: Path):
    settings = test_settings.model_copy(
        update={"resource_storage_root": str(tmp_path / "resource-store")}
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:15173") as client:
        yield SimpleNamespace(client=client, settings=settings, app=app)


async def publish_senior_chapter(db: AsyncSession):
    await import_package(db, load_package(LEGACY_PACKAGE), dry_run=False)
    revision = await revision_by_slug(db, SENIOR_COURSE, SENIOR_CHAPTER, 1)
    assert revision is not None
    await record_review(
        db,
        revision_id=revision.id,
        status=ReviewStatus.HUMAN_APPROVED,
        reviewer="human-reviewer-t21",
    )
    await publish_revision(db, revision_id=revision.id, actor="human-reviewer-t21")
    await db.commit()
    return revision


async def sign_in(aclient, *, username: str, stage: str, grade: int | None) -> str:
    await create_synthetic_user(
        aclient.settings,
        username=username,
        password=PASSWORD,
        role=UserRole.STUDENT,
        stage=stage,
        grade=grade,
    )
    token = await csrf(aclient.client)
    response = await login(aclient.client, username, PASSWORD, csrf_header=token)
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


# --------------------------------------------------------------------------- A1/A3
def test_registry_is_strict_and_only_known_templates_survive(tmp_path: Path) -> None:
    entries = load_definitions()
    ids = {entry["id"] for entry in entries}
    assert {
        SENIOR_ANIMATION,
        SEARCH_ANIMATION,
        DRAFT_ANIMATION,
        FIXTURE_ANIMATION,
    } <= ids
    assert {entry["template"] for entry in entries} <= {"SORT_STEPS", "BINARY_SEARCH"}
    # every registered definition declares bounded parameters
    for entry in entries:
        assert entry["param_schema"]["additional_properties"] is False
        assert entry["param_schema"]["required"]
        assert entry["limits"]["max_items"] > 0

    malicious = tmp_path / "definitions.json"
    malicious.write_text(
        json.dumps(
            {
                "schema_version": "k12.animation.definitions.v1",
                "limits": {"max_items": 5, "max_steps": 50, "min_value": 0, "max_value": 9},
                "definitions": [
                    {"id": "x-script", "template": "RUN_JS", "stage": "SENIOR"},
                    {
                        "id": "x-open",
                        "template": "SORT_STEPS",
                        "stage": "SENIOR",
                        "param_schema": {
                            "type": "object",
                            "additional_properties": True,
                            "required": ["values"],
                            "properties": {},
                        },
                    },
                    {"id": "x-stage", "template": "SORT_STEPS", "stage": "UNIVERSITY"},
                    "not-an-object",
                ],
            }
        ),
        encoding="utf-8",
    )
    assert load_definitions(malicious) == []


def forbidden_keys(
    payload: object, forbidden: tuple[str, ...] = ("code", "script", "html", "url")
) -> list[str]:
    """Recursively look for executable-looking payload keys (not substrings)."""

    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in forbidden:
                found.append(key)
            found.extend(forbidden_keys(value, forbidden))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(forbidden_keys(item, forbidden))
    return found


def test_registry_file_contains_no_executable_fields() -> None:
    raw = DEFINITIONS_PATH.read_text(encoding="utf-8")
    for token in ["<script", "javascript:", "eval(", "new Function", "http://", "https://"]:
        assert token not in raw
    payload = json.loads(raw)
    for entry in payload["definitions"]:
        assert "code" not in entry and "html" not in entry and "url" not in entry


# --------------------------------------------------------------------------- A2/A3
def test_parameter_boundaries_are_rejected() -> None:
    entry = next(item for item in load_definitions() if item["id"] == SEARCH_ANIMATION)
    assert validate_params(entry, {})["target"] == 7  # server-side defaults

    for params, code in [
        ({"values": [1, 2], "target": 1, "extra": 1}, "ANIMATION_PARAMS_UNKNOWN_KEY"),
        ({"values": [1, 2]}, "ANIMATION_PARAMS_MISSING"),
        ({"values": "1,2", "target": 1}, "ANIMATION_PARAMS_TYPE"),
        ({"values": [1, 1.5], "target": 1}, "ANIMATION_PARAMS_TYPE"),
        ({"values": [], "target": 1}, "ANIMATION_PARAMS_TOO_SHORT"),
        ({"values": list(range(20)), "target": 1}, "ANIMATION_PARAMS_TOO_LONG"),
        ({"values": [1, 2], "target": 100000}, "ANIMATION_PARAMS_RANGE"),
        ({"values": [1, 9999], "target": 1}, "ANIMATION_PARAMS_RANGE"),
    ]:
        with pytest.raises(AnimationParamsRejected) as rejected:
            validate_params(entry, params)
        assert rejected.value.code == code, params


# --------------------------------------------------------------------------- A6
@pytest.mark.asyncio
async def test_visibility_uses_publication_stage_and_chapter_truth(
    aclient, content_session
) -> None:
    viewer_senior = ViewerScope(stage=Stage.SENIOR, grade=11, profile=ContentProfile.DEVELOPMENT)

    # the bound chapter is not published yet -> no animation is offered
    await import_package(content_session, load_package(LEGACY_PACKAGE), dry_run=False)
    assert await visible_animations(content_session, viewer=viewer_senior) == []

    revision = await publish_senior_chapter(content_session)
    visible = await visible_animations(content_session, viewer=viewer_senior)
    ids = {entry["id"] for entry in visible}
    assert SENIOR_ANIMATION in ids and SEARCH_ANIMATION in ids
    # an unpublished (non-fixture) definition is never offered
    assert DRAFT_ANIMATION not in ids
    # an explicitly marked fixture is offered in development only
    assert FIXTURE_ANIMATION in ids

    formal = ViewerScope(stage=Stage.SENIOR, grade=11, profile=ContentProfile.FORMAL)
    formal_ids = {entry["id"] for entry in await visible_animations(content_session, viewer=formal)}
    assert FIXTURE_ANIMATION not in formal_ids
    assert {SENIOR_ANIMATION, SEARCH_ANIMATION} <= formal_ids

    # a junior student never sees a senior animation
    junior = ViewerScope(stage=Stage.JUNIOR, grade=8, profile=ContentProfile.DEVELOPMENT)
    assert await visible_animations(content_session, viewer=junior) == []

    # withdrawing the chapter hides the animations again
    await withdraw_revision(content_session, revision_id=revision.id, actor="human-reviewer-t21")
    await content_session.commit()
    assert await visible_animations(content_session, viewer=viewer_senior) == []

    with pytest.raises(AnimationNotVisible):
        await load_visible_animation(
            content_session, viewer=viewer_senior, identifier=SENIOR_ANIMATION
        )


@pytest.mark.asyncio
async def test_spec_is_data_only_and_rejects_illegal_parameters(aclient, content_session) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(aclient, username="t21.senior", stage="SENIOR", grade=11)
    assert revision is not None

    listed = await aclient.client.get("/api/v1/animations")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert {item["id"] for item in body["items"]} >= {SENIOR_ANIMATION, SEARCH_ANIMATION}
    for item in body["items"]:
        assert item["param_schema"]["additional_properties"] is False
        assert "code" not in item and "script" not in item

    ok = await aclient.client.post(
        f"/api/v1/animations/{SEARCH_ANIMATION}/spec",
        json={"params": {"values": [1, 3, 5, 7], "target": 5}},
        headers=auth_headers(token),
    )
    assert ok.status_code == 200, ok.text
    payload = ok.json()
    assert payload["step_source"] == "CLIENT_PURE_FUNCTION"
    assert payload["params"] == {"values": [1, 3, 5, 7], "target": 5}
    assert "steps" not in payload
    assert forbidden_keys(payload) == []

    too_long = await aclient.client.post(
        f"/api/v1/animations/{SEARCH_ANIMATION}/spec",
        json={"params": {"values": list(range(20)), "target": 1}},
        headers=auth_headers(token),
    )
    assert too_long.status_code == 422
    assert "ANIMATION_PARAMS_TOO_LONG" in too_long.text

    unknown_key = await aclient.client.post(
        f"/api/v1/animations/{SEARCH_ANIMATION}/spec",
        json={"params": {"values": [1, 2], "target": 1, "run": "alert(1)"}},
        headers=auth_headers(token),
    )
    assert unknown_key.status_code == 422
    assert "ANIMATION_PARAMS_UNKNOWN_KEY" in unknown_key.text

    # an unpublished draft is not addressable at all
    draft = await aclient.client.get(f"/api/v1/animations/{DRAFT_ANIMATION}")
    assert draft.status_code == 404 and "ANIMATION_NOT_VISIBLE" in draft.text
    draft_spec = await aclient.client.post(
        f"/api/v1/animations/{DRAFT_ANIMATION}/spec",
        json={"params": {}},
        headers=auth_headers(token),
    )
    assert draft_spec.status_code == 404

    # a fake template id cannot be used either
    faked = await aclient.client.post(
        "/api/v1/animations/anim-run-arbitrary-js/spec",
        json={"params": {}},
        headers=auth_headers(token),
    )
    assert faked.status_code == 404

    # writes need CSRF: the same call without a token is refused
    no_csrf = await aclient.client.post(
        f"/api/v1/animations/{SEARCH_ANIMATION}/spec",
        json={"params": {"values": [1, 2], "target": 1}},
        headers={"Origin": ORIGIN},
    )
    assert no_csrf.status_code == 403


@pytest.mark.asyncio
async def test_cross_stage_student_gets_no_animation(aclient, content_session) -> None:
    await publish_senior_chapter(content_session)
    await sign_in(aclient, username="t21.junior", stage="JUNIOR", grade=8)

    listed = await aclient.client.get("/api/v1/animations")
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    senior_id = SENIOR_ANIMATION
    detail = await aclient.client.get(f"/api/v1/animations/{senior_id}")
    assert detail.status_code == 404 and "ANIMATION_NOT_VISIBLE" in detail.text


@pytest.mark.asyncio
async def test_spec_matches_public_definition_shape(content_session) -> None:
    await publish_senior_chapter(content_session)
    viewer = ViewerScope(stage=Stage.SENIOR, grade=11, profile=ContentProfile.DEVELOPMENT)
    spec = await animation_spec(
        content_session,
        viewer=viewer,
        identifier=SENIOR_ANIMATION,
        params={"values": [3, 1, 2]},
    )
    assert spec["params"] == {"values": [3, 1, 2]}
    assert spec["definition"]["knowledge_points"] == ["sorting-algorithm"]
    assert spec["definition"]["chapter_slug"] == SENIOR_CHAPTER
    public = public_definition(
        next(item for item in load_definitions() if item["id"] == SENIOR_ANIMATION)
    )
    assert public["template"] == "SORT_STEPS"
    assert public["is_test_fixture"] is False and public["content_notice"] is None
    # the registry never leaks a server path or an executable field
    serialised = json.dumps(public, ensure_ascii=False)
    assert "/home/" not in serialised and "definitions.json" not in serialised
    assert (await content_session.scalar(select(1))) == 1


# --------------------------------------------------------------------------- A3 production path
@pytest.mark.asyncio
async def test_production_session_injects_only_visible_animation_ids(
    aclient, content_session
) -> None:
    """`create_session` must hand the Tutor the registry-filtered id set."""

    revision = await publish_senior_chapter(content_session)
    student = await create_synthetic_user(
        aclient.settings,
        username="t21.production",
        password=PASSWORD,
        role=UserRole.STUDENT,
        stage="SENIOR",
        grade=11,
    )
    session = await create_session(
        content_session,
        settings=aclient.settings,
        user=student,
        chapter_id=revision.chapter_id,
    )
    allowed = session.context["allowed_animation_ids"]
    assert SENIOR_ANIMATION in allowed and SEARCH_ANIMATION in allowed
    # unregistered / unpublished ids never appear
    assert DRAFT_ANIMATION not in allowed
    assert "anim-run-arbitrary-js" not in allowed
    for value in allowed:
        assert isinstance(value, str) and value.isascii()

    # a junior learner gets none of the senior animations
    await import_package(content_session, load_package(FIXTURE_PACKAGE), dry_run=False)
    junior = await create_synthetic_user(
        aclient.settings,
        username="t21.production.junior",
        password=PASSWORD,
        role=UserRole.STUDENT,
        stage="JUNIOR",
        grade=8,
    )
    junior_session = await create_session(
        content_session,
        settings=aclient.settings,
        user=junior,
        chapter_id=(
            await revision_by_slug(content_session, "t06-fixture-course", "ch02", 1)
        ).chapter_id,
    )
    assert junior_session.context["allowed_animation_ids"] == []


@pytest.mark.asyncio
async def test_animation_injection_is_fail_closed(aclient, content_session, monkeypatch) -> None:
    """A failing lookup must not fall back to chapter-body block ids."""

    revision = await publish_senior_chapter(content_session)
    student = await create_synthetic_user(
        aclient.settings,
        username="t21.failclosed",
        password=PASSWORD,
        role=UserRole.STUDENT,
        stage="SENIOR",
        grade=11,
    )

    async def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic animation lookup failure")

    monkeypatch.setattr("app.modules.teaching.service.visible_animations", boom)
    with pytest.raises(RuntimeError):
        await create_session(
            content_session,
            settings=aclient.settings,
            user=student,
            chapter_id=revision.chapter_id,
        )
    assert (await content_session.scalar(select(func.count()).select_from(LessonSession))) == 0


def test_context_without_injection_never_uses_block_animation_ids() -> None:
    """The chapter body cannot authorise an animation on its own."""

    blocks = [{"id": "anim-from-body", "type": "ANIMATION"}]
    without = build_session_context(
        chapter_slug="ch03",
        chapter_id="00000000-0000-0000-0000-000000000001",
        chapter_title="算法",
        revision_number=1,
        revision_id="00000000-0000-0000-0000-000000000002",
        stage="SENIOR",
        objectives=["o"],
        blocks=blocks,
    )
    assert without["allowed_animation_ids"] == []

    injected = build_session_context(
        chapter_slug="ch03",
        chapter_id="00000000-0000-0000-0000-000000000001",
        chapter_title="算法",
        revision_number=1,
        revision_id="00000000-0000-0000-0000-000000000002",
        stage="SENIOR",
        objectives=["o"],
        blocks=blocks,
        authorized_animation_ids=[
            "anim-sort-bubble-v1",
            "https://evil.example/x",
            "bad id",
        ],
    )
    # only well-formed registry-shaped ids survive; URLs and prose are dropped
    assert injected["allowed_animation_ids"] == ["anim-sort-bubble-v1"]
