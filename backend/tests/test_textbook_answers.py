from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.modules.content.book_import import Answers, validate_books
from app.modules.content.importer import ContentImportError, import_package
from app.modules.content.models import ChapterRevision, ContentProfile, ReadingEvent, TextbookAnswer
from app.modules.content.package import PackageValidationError, load_package, revision_snapshot
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import visible_courses, visible_self_test_answer, withdraw_revision
from app.modules.content.textbook_answers import question_locators, validated_answer_bundles
from app.modules.identity.models import Stage
from tests.identity_helpers import create_synthetic_user, csrf, login, write_headers

ROOT = Path(__file__).resolve().parents[2] / "curriculum/source/original/original-books-v1"


def test_all_432_questions_and_576_stage_associations_are_exact():
    package = load_package(ROOT)
    source = validate_books(ROOT / "source")
    bundles = validated_answer_bundles(package)
    assert len(bundles) == 96
    assert sum(len(b.answers.answers) for b in bundles) == 576
    assert (
        len({(b.answers.chapter_id, a.question_id) for b in bundles for a in b.answers.answers})
        == 432
    )
    for item, bundle in zip(package.chapters, bundles, strict=True):
        body = [b.model_dump(mode="json", exclude_none=True) for b in item.blocks]
        questions = question_locators(body)
        assert len(questions) == 6
        for q, answer in zip(questions, bundle.answers.answers, strict=True):
            assert (q.question_id, q.question_type) == (answer.question_id, answer.type)
            end_index = int(q.end_block_id[1:]) - 1
            text = body[end_index]["text"]
            # Offset is before the next question/section, not inside a code fence.
            assert 0 < q.end_offset <= len(text)
            tail = text[q.end_offset :].lstrip()
            assert not tail or tail.startswith(("### Q", "## 本章小结"))
        public = json.dumps(revision_snapshot(package, item), ensure_ascii=False)
        assert "reference_answer" not in public and "correct_options" not in public
        assert "answers/" not in public
    assert (
        sum(
            len(Answers.model_validate_json(raw).answers)
            for p, raw in source.files.items()
            if p.startswith("answers/")
        )
        == 432
    )


def test_locators_ignore_other_sections_and_fenced_fake_headings():
    text = "## 知识讲解\n\n### Q01 · 单选题\n\n普通问题\n\n## 练习与自测\n\n"
    for i in range(1, 7):
        label = ["单选题", "简答题", "实践题"][(i - 1) // 2]
        text += f"### Q{i:02} · {label}\n\n题目😀{i}\n\n"
        if i == 3:
            text += "```text\n### Q01 · 单选题\n```\n\n"
    text += "## 本章小结\n\n结束"
    q = question_locators([{"type": "MARKDOWN", "text": text}])
    assert len(q) == 6
    assert text[q[0].end_offset :].startswith("### Q02")
    assert text[q[-1].end_offset :].startswith("## 本章小结")
    assert question_locators([{"type": "MARKDOWN", "text": "### Q01 · 单选题\n普通问题"}]) == []


@pytest.mark.parametrize(
    "mutation", ["missing", "checksum", "type", "body", "stage", "conversion", "inventory"]
)
@pytest.mark.asyncio
async def test_invalid_source_refuses_import_before_any_write(tmp_path, content_session, mutation):
    root = tmp_path / "package"
    shutil.copytree(ROOT, root)
    package = load_package(root)
    answer_file = root / "source/answers/primary-computing/01.json"
    if mutation == "missing":
        answer_file.unlink()
    elif mutation == "inventory":
        (root / "inventory.json").write_text("{}")
    elif mutation in {"checksum", "type"}:
        payload = json.loads(answer_file.read_text())
        if mutation == "checksum":
            payload["answers"][0]["reference_answer"] += "不可替换已有固定答案"
        else:
            payload["answers"][0]["type"] = "PRACTICE"
        answer_file.write_text(json.dumps(payload, ensure_ascii=False))
    else:
        item = package.chapters[0]
        if mutation == "body":
            blocks = list(item.blocks)
            blocks[-1] = blocks[-1].model_copy(update={"text": blocks[-1].text + "\n\n修改内容"})
            item = replace(item, blocks=tuple(blocks))
        elif mutation == "stage":
            item = replace(item, spec=item.spec.model_copy(update={"stage": Stage.SENIOR}))
        else:
            item = replace(
                item,
                spec=item.spec.model_copy(
                    update={"source": item.spec.source.model_copy(update={"conversion": "other"})}
                ),
            )
        package = replace(package, chapters=(item, *package.chapters[1:]))
    with pytest.raises(PackageValidationError):
        await import_package(content_session, package, dry_run=False)
    assert await content_session.scalar(select(func.count()).select_from(ChapterRevision)) == 0
    assert await content_session.scalar(select(func.count()).select_from(TextbookAnswer)) == 0


@pytest.mark.asyncio
async def test_first_repeat_and_backfill_preserve_revision_and_progress(
    content_session, client, test_settings
):
    package = load_package(ROOT)
    dry = await import_package(content_session, package)
    assert dry.counters["answers_created"] == 576
    assert await content_session.scalar(select(func.count()).select_from(TextbookAnswer)) == 0
    first = await import_package(content_session, package, dry_run=False)
    assert first.counters["answers_created"] == 576
    revisions = {
        r.id: (r.content_hash, r.body)
        for r in (await content_session.scalars(select(ChapterRevision))).all()
    }
    await create_synthetic_user(
        test_settings,
        username="answers.progress",
        password="synthetic-pass-1",
        stage="JUNIOR",
        grade=8,
    )
    await login(client, "answers.progress", "synthetic-pass-1")
    chapter = (await client.get("/api/v1/courses")).json()["items"][0]["chapters"][0]
    event = await client.post(
        "/api/v1/reading-events",
        headers=write_headers(await csrf(client)),
        json={
            "client_event_id": "answers-backfill-progress",
            "chapter_id": chapter["chapter_id"],
            "revision": 1,
            "event_kind": "BLOCK_VIEW",
            "block_id": "b3",
        },
    )
    assert event.status_code == 200, event.text
    again = await import_package(content_session, package, dry_run=False)
    assert again.counters["answers_created"] == 0 and again.counters["answers_reused"] == 576
    # An existing pre-feature import has the same immutable revisions, no answer rows.
    await content_session.execute(delete(TextbookAnswer))
    await content_session.commit()
    detail = (await client.get(f"/api/v1/chapters/{chapter['chapter_id']}")).json()
    assert len(detail["self_test_questions"]) == 6
    assert not any(q["has_reference_answer"] for q in detail["self_test_questions"])
    assert (
        await client.get(
            f"/api/v1/chapters/{chapter['chapter_id']}/self-test-answers/Q01"
            f"?revision_id={chapter['revision_id']}"
        )
    ).status_code == 404
    backfill = await import_package(content_session, package, dry_run=False)
    assert (
        backfill.counters["revisions_created"] == 0 and backfill.counters["answers_created"] == 576
    )
    assert await content_session.scalar(select(func.count()).select_from(ReadingEvent)) == 1
    assert revisions == {
        r.id: (r.content_hash, r.body)
        for r in (await content_session.scalars(select(ChapterRevision))).all()
    }
    # Existing private content is never silently overwritten.
    row = await content_session.scalar(select(TextbookAnswer))
    row.explanation += "差异"
    await content_session.commit()
    with pytest.raises(ContentImportError):
        await import_package(content_session, package, dry_run=False)


@pytest.mark.parametrize("stage", list(Stage))
@pytest.mark.asyncio
async def test_single_answer_permissions_public_projection_and_fields(
    content_session, client, test_settings, stage
):
    await import_package(content_session, load_package(ROOT), dry_run=False)
    viewer = ViewerScope(stage=stage, grade=None, profile=ContentProfile.DEVELOPMENT)
    courses = await visible_courses(content_session, viewer)
    chapter = courses[0].chapters[0]
    url = f"/api/v1/chapters/{chapter.chapter_id}/self-test-answers"
    query = f"?revision_id={chapter.revision_id}"
    assert (await client.get(url + "/Q01" + query)).status_code == 401
    await create_synthetic_user(
        test_settings,
        username="answers.reader",
        password="synthetic-pass-1",
        stage=stage.value,
        grade=None,
    )
    await login(client, "answers.reader", "synthetic-pass-1")
    detail = await client.get(f"/api/v1/chapters/{chapter.chapter_id}")
    assert len(detail.json()["self_test_questions"]) == 6
    for public in [
        detail,
        await client.get("/api/v1/courses"),
        await client.get("/api/v1/learning/catalog"),
    ]:
        assert "reference_answer" not in public.text.replace("has_reference_answer", "")
        assert "correct_options" not in public.text and "answers/" not in public.text
    for i in range(1, 7):
        result = await client.get(url + f"/Q{i:02}" + query)
        assert result.status_code == 200
        data = result.json()
        assert set(data) == {
            "chapter_id",
            "revision_id",
            "revision",
            "question_id",
            "question_type",
            "correct_options",
            "reference_answer",
            "explanation",
        }
        assert data["revision_id"] == str(chapter.revision_id)
        assert len(data["correct_options"]) == (1 if i <= 2 else 0)
        row = await content_session.get(TextbookAnswer, (chapter.revision_id, f"Q{i:02}"))
        assert data["reference_answer"] == row.reference_answer
        assert data["explanation"] == row.explanation
    for qid in ["Q00", "Q07", "q01", "Q1", "unknown"]:
        assert (await client.get(url + "/" + qid + query)).status_code == 404
    assert (await client.get(url + "/Q01")).status_code == 422
    assert (await client.get(url + "/Q01?revision_id=" + str(uuid.uuid4()))).status_code == 404
    other = courses[0].chapters[1]
    assert (await client.get(url + f"/Q01?revision_id={other.revision_id}")).status_code == 404
    wrong_stage = next(s for s in Stage if s != stage)
    hidden = (
        await visible_courses(
            content_session,
            ViewerScope(stage=wrong_stage, grade=None, profile=ContentProfile.DEVELOPMENT),
        )
    )[0].chapters[0]
    assert (
        await client.get(
            f"/api/v1/chapters/{hidden.chapter_id}/self-test-answers/Q01?revision_id={hidden.revision_id}"
        )
    ).status_code == 404
    assert (
        await visible_self_test_answer(
            content_session,
            chapter_id=chapter.chapter_id,
            revision_id=chapter.revision_id,
            question_id="Q01",
            viewer=ViewerScope(stage=stage, grade=None, profile=ContentProfile.FORMAL),
        )
        is None
    )
    await withdraw_revision(
        content_session, revision_id=chapter.revision_id, actor="合成测试撤回者"
    )
    response = await client.get(url + "/Q01" + query)
    assert response.status_code == 404
    assert "answers/" not in response.text and "reference_answer" not in response.text


@pytest.mark.asyncio
async def test_requested_revision_is_used_even_when_newer_exists(content_session):
    package = load_package(ROOT)
    await import_package(content_session, package, dry_run=False)
    # Same verified source can have a distinct immutable revision. Public latest
    # must not replace the explicit revision supplied by the reading page.
    revised = replace(
        package,
        chapters=tuple(
            replace(c, spec=c.spec.model_copy(update={"revision": 2})) for c in package.chapters
        ),
    )
    await import_package(content_session, revised, dry_run=False)
    old = await content_session.scalar(
        select(ChapterRevision).where(
            ChapterRevision.revision == 1, ChapterRevision.stage == "JUNIOR"
        )
    )
    new = await content_session.scalar(
        select(ChapterRevision).where(
            ChapterRevision.revision == 2, ChapterRevision.chapter_id == old.chapter_id
        )
    )
    viewer = ViewerScope(stage=Stage.JUNIOR, grade=8, profile=ContentProfile.DEVELOPMENT)
    for rev in (old, new):
        answer = await visible_self_test_answer(
            content_session,
            chapter_id=old.chapter_id,
            revision_id=rev.id,
            question_id="Q01",
            viewer=viewer,
        )
        assert answer.revision_id == rev.id and answer.revision == rev.revision
    assert await content_session.scalar(select(func.count()).select_from(TextbookAnswer)) == 1152
