"""T22 acceptance: the authoring closed loop.

V1 durable jobs · V2 asset_request is not an artefact / no file ⇒ no completion ·
V3 only a real human review can approve · V4 publish creates a new immutable
revision and updates the bundle · V5 retry budget, cancel and publish
idempotency · V6 Designer has no learner-data or account write access ·
V8 honest platform claims.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.main import create_app
from app.modules.authoring.material import (
    AuthoringMaterial,
    build_package_request,
)
from app.modules.authoring.models import (
    AuthoringArtifact,
    AuthoringPackage,
    AuthoringPublication,
    AuthoringReview,
)
from app.modules.authoring.service import approve_package
from app.modules.content.importer import import_package
from app.modules.content.models import ReviewStatus
from app.modules.content.package import load_package
from app.modules.content.service import publish_revision, record_review, withdraw_revision
from app.modules.identity.models import User, UserRole
from tests.content_helpers import LEGACY_PACKAGE, revision_by_slug
from tests.identity_helpers import (
    auth_headers,
    create_synthetic_user,
    csrf,
    login,
)

PASSWORD = "synthetic-T22-Pass-1234"
SENIOR_COURSE, SENIOR_CHAPTER = "algorithm-everyday", "ch03"
LEARNER_TABLES = ("learning_evidence", "learning_evidence_items", "learning_observations")


@pytest_asyncio.fixture
async def actx(test_settings: Settings, tmp_path: Path):
    settings = test_settings.model_copy(
        update={
            "gateway_mode": "fixture",
            "authoring_artifact_root": str(tmp_path / "artifacts"),
            "authoring_bundle_root": str(tmp_path / "bundle"),
            "authoring_max_attempts": 2,
        }
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
        reviewer="human-reviewer-t22",
    )
    await publish_revision(db, revision_id=revision.id, actor="human-reviewer-t22")
    await db.commit()
    return revision


async def sign_in(
    actx, *, username: str, role: UserRole = UserRole.ADMIN, stage="SENIOR", grade=11
):
    await create_synthetic_user(
        actx.settings,
        username=username,
        password=PASSWORD,
        role=role,
        stage=stage if role == UserRole.STUDENT else None,
        grade=grade if role == UserRole.STUDENT else None,
    )
    token = await csrf(actx.client)
    response = await login(actx.client, username, PASSWORD, csrf_header=token)
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


async def wait_for_job(actx, job_id: str, *, timeout: float = 10.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        body = (await actx.client.get(f"/api/v1/admin/authoring/jobs/{job_id}")).json()
        if body["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return body
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(f"job did not settle: {body}")
        await asyncio.sleep(0.05)


async def create_and_run(actx, token: str, revision_id) -> tuple[dict, str]:
    created = await actx.client.post(
        "/api/v1/admin/authoring/jobs",
        json={
            "chapter_revision_id": str(revision_id),
            "idempotency_key": f"job-{uuid.uuid4().hex[:8]}",
        },
        headers=auth_headers(token),
    )
    assert created.status_code == 201, created.text
    job = await wait_for_job(actx, created.json()["id"])
    assert job["status"] == "SUCCEEDED", job
    return job, job["package_id"]


# --------------------------------------------------------------------------- V1
@pytest.mark.asyncio
async def test_v1_designer_job_records_status_attempt_and_run(actx, content_session) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.admin")

    key = f"job-{uuid.uuid4().hex[:8]}"
    first = await actx.client.post(
        "/api/v1/admin/authoring/jobs",
        json={"chapter_revision_id": str(revision.id), "idempotency_key": key},
        headers=auth_headers(token),
    )
    assert first.status_code == 201, first.text
    # same idempotency key -> same job, never a second run
    again = await actx.client.post(
        "/api/v1/admin/authoring/jobs",
        json={"chapter_revision_id": str(revision.id), "idempotency_key": key},
        headers=auth_headers(token),
    )
    assert again.json()["id"] == first.json()["id"]

    job = await wait_for_job(actx, first.json()["id"])
    assert job["status"] == "SUCCEEDED", job
    assert job["attempt"] == 1 and job["max_attempts"] >= 1
    assert job["run_ref"] and job["run_ref"].startswith("designer-")

    detail = await actx.client.get(f"/api/v1/admin/authoring/packages/{job['package_id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["spec"]["schema_version"] == "k12.lesson.package.draft.v1"
    assert body["status"] in {"AUTO_VALIDATED", "DRAFT"}
    assert {item["kind"] for item in body["artifacts"]} == {
        "LESSON_MARKDOWN",
        "PACKAGE_MANIFEST",
    }
    assert all(item["verified"] for item in body["artifacts"])


# ------------------------------------------------------- V1b request/schema truth
def test_v1b_designer_request_matches_the_frozen_contract() -> None:
    """The local request builder is *validated*, never guessed from a platform doc."""

    material = AuthoringMaterial(
        chapter_id=uuid.uuid4(),
        revision_id=uuid.uuid4(),
        chapter_slug="synthetic-slug",
        chapter_title="合成章节",
        revision_number=1,
        curriculum_revision="synthetic-slug:r1",
        stage="SENIOR",
        objectives=("说明相邻比较与交换",),
        knowledge_context=(
            {
                "source_id": "chapter:synthetic-slug",
                "revision": "1",
                "locator": "block:0",
                "text": "合成正文，用于协议自检。",
            },
        ),
    )
    request = build_package_request(material, request_id="designer-schema-check-1")
    errors = default_registry().validate_request(Operation.LESSON_PACKAGE_DRAFT, request)
    assert errors == [], errors
    assert request["operation"] == "LESSON_PACKAGE_DRAFT"
    assert request["quiz_spec"] is None
    assert request["lesson_spec"]["asset_requests_allowed"] is True


@pytest.mark.asyncio
async def test_v1b_job_creation_fails_closed_on_unusable_revision(actx, content_session) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.v1b.admin")

    missing = await actx.client.post(
        "/api/v1/admin/authoring/jobs",
        json={
            "chapter_revision_id": str(uuid.uuid4()),
            "idempotency_key": f"job-{uuid.uuid4().hex[:8]}",
        },
        headers=auth_headers(token),
    )
    assert missing.status_code == 404, missing.text
    assert "AUTHORING_REVISION_NOT_FOUND" in missing.text

    # withdraw the revision: no new job may be created against it
    await withdraw_revision(content_session, revision_id=revision.id, actor="human-reviewer-t22")
    await content_session.commit()
    withdrawn = await actx.client.post(
        "/api/v1/admin/authoring/jobs",
        json={
            "chapter_revision_id": str(revision.id),
            "idempotency_key": f"job-{uuid.uuid4().hex[:8]}",
        },
        headers=auth_headers(token),
    )
    assert withdrawn.status_code == 422, withdrawn.text
    assert "AUTHORING_REVISION_WITHDRAWN" in withdrawn.text


# --------------------------------------------------------------------------- V2
@pytest.mark.asyncio
async def test_v2_asset_requests_are_not_artifacts_and_missing_file_blocks(
    actx, content_session
) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.v2.admin")
    job, package_id = await create_and_run(actx, token, revision.id)

    detail = (await actx.client.get(f"/api/v1/admin/authoring/packages/{package_id}")).json()
    # the Designer asked for artwork/video …
    assert detail["asset_requests"], "fixture spec should contain asset requests"
    # … and none of those become artefacts
    kinds = {item["kind"] for item in detail["artifacts"]}
    assert kinds == {"LESSON_MARKDOWN", "PACKAGE_MANIFEST"}

    package_uuid = uuid.UUID(package_id)
    artifact = await content_session.scalar(
        select(AuthoringArtifact).where(AuthoringArtifact.package_id == package_uuid)
    )
    real_path = Path(actx.settings.authoring_artifact_root) / artifact.storage_key
    assert real_path.is_file()
    assert hashlib.sha256(real_path.read_bytes()).hexdigest() == artifact.sha256

    # a missing file must block approval entirely
    real_path.unlink()
    missing = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/approve",
        json={"comment": "文件缺失"},
        headers=auth_headers(token),
    )
    assert missing.status_code == 409, missing.text
    assert "AUTHORING_NO_VERIFIED_ARTIFACT" in missing.text

    package = await content_session.scalar(
        select(AuthoringPackage).where(AuthoringPackage.id == package_uuid)
    )
    await content_session.refresh(package)
    assert package.status != "HUMAN_APPROVED"
    assert job["status"] == "SUCCEEDED"


# --------------------------------------------------------------------------- V3
@pytest.mark.asyncio
async def test_v3_only_real_human_review_can_approve(actx, content_session) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.v3.admin")
    _job, package_id = await create_and_run(actx, token, revision.id)
    package = await content_session.scalar(
        select(AuthoringPackage).where(AuthoringPackage.id == uuid.UUID(package_id))
    )

    # (a) automation / anonymous actor is refused in the service layer
    for actor in (None,):
        with pytest.raises(Exception) as refused:
            await approve_package(
                content_session, settings=actx.settings, package=package, actor=actor
            )
        assert "AUTHORING_HUMAN_ONLY" in str(refused.value)

    # (b) a real admin may approve, and the review row is what makes it valid
    admin = await content_session.scalar(select(User).where(User.username == "t22.v3.admin"))
    review = await approve_package(
        content_session, settings=actx.settings, package=package, actor=admin
    )
    assert review.actor_kind == "HUMAN_ADMIN" and review.actor_user_id == admin.id
    await content_session.refresh(package)
    assert package.status == "HUMAN_APPROVED"

    # (c) the database itself refuses a self-approval without a review row
    self_approved = AuthoringPackage(
        job_id=package.job_id,
        chapter_revision_id=package.chapter_revision_id,
        title="self approved",
        spec={},
        asset_requests=[],
        status="HUMAN_APPROVED",
        revision=1,
    )
    content_session.add(self_approved)
    with pytest.raises(Exception) as guard:
        await content_session.flush()
    assert "requires a real human review row" in str(guard.value)
    await content_session.rollback()

    # (d) a student session cannot even reach the admin surface
    await content_session.rollback()
    student_token = await sign_in(actx, username="t22.v3.student", role=UserRole.STUDENT)
    forbidden = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/approve",
        json={"comment": "假的"},
        headers=auth_headers(student_token),
    )
    assert forbidden.status_code == 403


# --------------------------------------------------------------------------- V4
@pytest.mark.asyncio
async def test_v4_publish_is_a_new_immutable_revision_and_updates_bundle(
    actx, content_session
) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.v4.admin")
    _job, package_id = await create_and_run(actx, token, revision.id)
    package_uuid = uuid.UUID(package_id)

    # publishing before approval is refused
    early = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/publish",
        json={"idempotency_key": f"pub-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers(token),
    )
    assert early.status_code == 409 and "AUTHORING_NOT_APPROVED" in early.text

    approved = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/approve",
        json={"comment": "人工审校通过"},
        headers=auth_headers(token),
    )
    assert approved.status_code == 200, approved.text

    first_key = f"pub-{uuid.uuid4().hex[:8]}"
    first = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/publish",
        json={"idempotency_key": first_key},
        headers=auth_headers(token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert first.json()["publication"]["revision"] == 1

    bundle_root = Path(actx.settings.authoring_bundle_root)
    index = json.loads((bundle_root / "index.json").read_text(encoding="utf-8"))
    assert len(index["entries"]) == 1
    entry_one = index["entries"][0]
    first_bundle_bytes = (bundle_root / entry_one["path"]).read_bytes()

    # a second, distinct publish intent makes revision 2 and keeps revision 1
    second = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/publish",
        json={"idempotency_key": f"pub-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers(token),
    )
    assert second.status_code == 200 and second.json()["publication"]["revision"] == 2
    index = json.loads((bundle_root / "index.json").read_text(encoding="utf-8"))
    assert [item["package_revision"] for item in index["entries"]] == [1, 2]
    # revision 1 bundle is byte-identical: old lessons keep their old version
    assert (bundle_root / entry_one["path"]).read_bytes() == first_bundle_bytes

    publications = list(
        await content_session.scalars(
            select(AuthoringPublication).where(AuthoringPublication.package_id == package_uuid)
        )
    )
    assert sorted(item.revision for item in publications) == [1, 2]
    for item in publications:
        assert item.published_by_user_id is not None
        assert item.artifact_sha256


# --------------------------------------------------------------------------- V5
@pytest.mark.asyncio
async def test_v5_retry_budget_cancel_and_publish_idempotency(actx, content_session) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.v5.admin")

    # gateway disabled -> the job fails, and the retry budget is enforced
    actx.app.state.settings = actx.settings.model_copy(update={"gateway_mode": "disabled"})
    try:
        created = await actx.client.post(
            "/api/v1/admin/authoring/jobs",
            json={
                "chapter_revision_id": str(revision.id),
                "idempotency_key": f"job-{uuid.uuid4().hex[:8]}",
                "max_attempts": 1,
            },
            headers=auth_headers(token),
        )
        job_id = created.json()["id"]
        failed = await wait_for_job(actx, job_id)
        assert failed["status"] == "FAILED" and failed["attempt"] == 1
        # the recorded code is the honest gateway reason (disabled ⇒ no call,
        # no fallback), never a fabricated success or a generic guess
        assert failed["error_code"] in {
            "AUTHORING_GATEWAY_FAILED",
            "AUTHORING_GATEWAY_DISABLED",
            "GATEWAY_DISABLED",
        }
        retried = await actx.client.post(
            f"/api/v1/admin/authoring/jobs/{job_id}/retry", headers=auth_headers(token)
        )
        assert retried.status_code == 409
        assert "AUTHORING_RETRY_BUDGET_EXHAUSTED" in retried.text
    finally:
        actx.app.state.settings = actx.settings

    # cancel is idempotent
    queued = await actx.client.post(
        "/api/v1/admin/authoring/jobs",
        json={
            "chapter_revision_id": str(revision.id),
            "idempotency_key": f"job-{uuid.uuid4().hex[:8]}",
        },
        headers=auth_headers(token),
    )
    job_id = queued.json()["id"]
    first_cancel = await actx.client.post(
        f"/api/v1/admin/authoring/jobs/{job_id}/cancel", headers=auth_headers(token)
    )
    second_cancel = await actx.client.post(
        f"/api/v1/admin/authoring/jobs/{job_id}/cancel", headers=auth_headers(token)
    )
    assert first_cancel.json()["status"] == "CANCELLED"
    assert second_cancel.json()["status"] == "CANCELLED"

    # publish idempotency: the same key never produces a second revision
    _job, package_id = await create_and_run(actx, token, revision.id)
    await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/approve",
        json={"comment": "ok"},
        headers=auth_headers(token),
    )
    key = f"pub-{uuid.uuid4().hex[:8]}"
    one = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/publish",
        json={"idempotency_key": key},
        headers=auth_headers(token),
    )
    two = await actx.client.post(
        f"/api/v1/admin/authoring/packages/{package_id}/publish",
        json={"idempotency_key": key},
        headers=auth_headers(token),
    )
    assert one.json()["created"] is True and two.json()["created"] is False
    assert one.json()["publication"]["revision"] == two.json()["publication"]["revision"]

    # and a *later* real publish still starts from the frozen approval snapshots
    assert (
        await content_session.scalar(
            select(func.count())
            .select_from(AuthoringPublication)
            .where(AuthoringPublication.package_id == uuid.UUID(package_id))
        )
        == 1
    )


# --------------------------------------------------------------------------- V6
@pytest.mark.asyncio
async def test_v6_designer_cannot_write_learner_or_account_data(actx, content_session) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.v6.admin")

    async def counts() -> dict[str, int]:
        result = {}
        for table in LEARNER_TABLES:
            result[table] = await content_session.scalar(text(f"SELECT count(*) FROM {table}"))
        result["identity_users"] = await content_session.scalar(
            text("SELECT count(*) FROM identity_users")
        )
        return result

    before = await counts()
    job, _package_id = await create_and_run(actx, token, revision.id)
    assert job["status"] == "SUCCEEDED"
    after = await counts()
    assert after == before

    # the authoring surface itself is admin-only
    student_token = await sign_in(actx, username="t22.v6.student", role=UserRole.STUDENT)
    blocked = await actx.client.post(
        "/api/v1/admin/authoring/jobs",
        json={"chapter_revision_id": str(revision.id), "idempotency_key": "student-attempt"},
        headers=auth_headers(student_token),
    )
    assert blocked.status_code == 403


# --------------------------------------------------------------------------- V8
@pytest.mark.asyncio
async def test_v8_honest_platform_claims(actx, content_session) -> None:
    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.v8.admin")
    _job, package_id = await create_and_run(actx, token, revision.id)
    detail = await actx.client.get(f"/api/v1/admin/authoring/packages/{package_id}")
    text_body = detail.text

    # no claim that the platform generated slides/images/video
    for claim in ["generated_video", "generated_image", "generated_slides", "ppt_generated"]:
        assert claim not in text_body
    assert "asset_requests" in text_body
    assert "不是产物" in text_body

    # The stable invariant is the *gate*: no real human content review has
    # happened, so G_HUMAN_CONTENT_REVIEW stays BLOCKED. The task status is
    # process state owned by the supervisor (it flips to DONE after review), so
    # asserting it here made this test self-referential — see T22 repair
    # attempt 2 (dispatch 23896ba1-8f81-442e-bf9e-68bcfcc6fbb1).
    progress = json.loads(
        (Path(__file__).resolve().parents[2] / ".rebuild-kit/progress.json").read_text("utf-8")
    )
    assert progress["gates"]["G_HUMAN_CONTENT_REVIEW"]["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_local_renderer_is_deterministic(actx, content_session) -> None:
    """The same spec renders byte-identical files (V2 evidence)."""

    revision = await publish_senior_chapter(content_session)
    token = await sign_in(actx, username="t22.det.admin")
    _job, first_id = await create_and_run(actx, token, revision.id)
    _job2, second_id = await create_and_run(actx, token, revision.id)

    async def digests(package_id: str) -> dict[str, str]:
        rows = list(
            await content_session.scalars(
                select(AuthoringArtifact).where(
                    AuthoringArtifact.package_id == uuid.UUID(package_id)
                )
            )
        )
        return {row.kind: row.sha256 for row in rows}

    assert await digests(first_id) == await digests(second_id)
    assert (await content_session.scalar(select(func.count()).select_from(AuthoringReview))) == 0
