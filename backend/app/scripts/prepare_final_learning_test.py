"""Add four explicitly synthetic lesson/Designer fixtures to an isolated test DB.

Run after prepare_learning_browser_test. No student answers, scores, phase
events or finished sessions are inserted: the browser must produce those via
the normal authenticated APIs. This does not call real Knodo.
"""

import asyncio
import copy
import json
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.core.test_database import validate_test_database_url
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.types import GatewayResult, GatewayStatus, GatewayUsage
from app.modules.assessment.models import QuizDraft
from app.modules.assessment.service import create_quiz_draft_job
from app.modules.content.importer import import_package
from app.modules.content.package import load_package, sha256_bytes
from app.modules.content.schemas import ViewerScope
from app.modules.content.service import content_profile_for, visible_courses
from app.modules.identity.models import PreferredStyle, Stage, UserRole
from app.modules.identity.service import ensure_demo_user

ROOT = Path(__file__).resolve().parents[3]
COURSE = "final-learning-fixture"
STAGES = {
    "PRIMARY_LOWER": (1, 3, "小学低段"),
    "PRIMARY_UPPER": (4, 6, "小学高段"),
    "JUNIOR": (7, 9, "初中"),
    "SENIOR": (10, 12, "高中"),
}
QUESTION_TYPES = {
    "PRIMARY_LOWER": ["TRUE_FALSE"],
    "PRIMARY_UPPER": ["SINGLE_CHOICE", "TRUE_FALSE"],
    "JUNIOR": ["SINGLE_CHOICE", "ORDERING", "SINGLE_CHOICE"],
    "SENIOR": ["SINGLE_CHOICE", "ORDERING", "SINGLE_CHOICE"],
}


def write_fixture(root):
    source = ROOT / "curriculum/source/synthetic/t06-fixtures-v1"
    template = json.loads((source / "courses/t06-fixture-course/course.json").read_text())
    body_template = json.loads(
        (source / "courses/t06-fixture-course/chapters/ch01.json").read_text()
    )
    course = {
        **template,
        "stable_slug": COURSE,
        "title": "最终学习联验（合成夹具）",
        "chapters": [],
    }
    for index, (stage, (low, high, label)) in enumerate(STAGES.items(), 1):
        slug, title = stage.lower().replace("_", "-"), f"联验合成课堂 · {label}"
        chapter = copy.deepcopy(template["chapters"][0])
        body = copy.deepcopy(body_template)
        body["chapter"], body["blocks"][0]["text"] = slug, title
        raw = (json.dumps(body, ensure_ascii=False, indent=2) + "\n").encode()
        path = root / f"courses/{COURSE}/chapters/{slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        chapter.update(
            stable_slug=slug,
            title=title,
            stage=stage,
            grade_min=low,
            grade_max=high,
            order_index=index,
            content_file=f"chapters/{slug}.json",
        )
        chapter["source"]["source_path"] = f"courses/{COURSE}/chapters/{slug}.json"
        chapter["source"]["original_sha256"] = sha256_bytes(raw)
        course["chapters"].append(chapter)
    (root / f"courses/{COURSE}/course.json").write_text(
        json.dumps(course, ensure_ascii=False, indent=2) + "\n"
    )
    release = json.loads((source / "release.json").read_text())
    release.update(
        release_key="synthetic-final-learning-v1",
        course_files=[f"courses/{COURSE}/course.json"],
        description="仅用于最终学习流程联验；不是正式教材或真实 AI 生成结果。",
    )
    (root / "release.json").write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n")


class FinalFixtureDesigner:
    mode = "fixture"

    async def invoke(self, operation, request, **_kwargs):
        assert operation is Operation.QUIZ_DRAFT
        stage = request["stage"]
        kinds = QUESTION_TYPES[stage]
        assert len(kinds) == request["quiz_spec"]["count"]
        assert all(kind in request["quiz_spec"]["question_types"] for kind in kinds)
        source = request["knowledge_context"][0]
        refs = [{key: source[key] for key in ("source_id", "revision", "locator")}]
        questions = []
        for index, kind in enumerate(kinds, 1):
            question = {
                "question_key": f"final-{stage.lower()}-{index}",
                "objective_id": request["objective_ids"][0],
                "stem": f"联验 {stage} Q{index:02}：先观察，再判断，最后动手。",
                "explanation": "联验合成解析：先观察，再判断，最后动手。",
                "hints": [
                    "联验提示一：先观察题干。",
                    "联验提示二：比较选项。",
                    "联验提示三：检查步骤。",
                ],
                "source_refs": refs,
                "type": kind,
            }
            if kind == "SINGLE_CHOICE":
                question.update(
                    options=[{"key": "A", "text": "先观察再判断"}, {"key": "B", "text": "直接猜"}],
                    correct_answer="A",
                )
            elif kind == "TRUE_FALSE":
                question["correct_answer"] = True
            else:
                question.update(
                    items=[
                        {"key": "A", "text": "观察"},
                        {"key": "B", "text": "判断"},
                        {"key": "C", "text": "动手"},
                    ],
                    correct_order=["A", "B", "C"],
                )
            questions.append(question)
        output = {
            "schema_version": "k12.quiz.draft.v1",
            **{
                key: request[key]
                for key in ("request_id", "chapter_id", "curriculum_revision", "stage")
            },
            "difficulty": request["quiz_spec"]["difficulty"],
            "questions": questions,
            "warnings": [],
        }
        return GatewayResult(
            invocation_id=str(uuid.uuid4()),
            operation=operation,
            mode="fixture",
            status=GatewayStatus.OK,
            output=output,
            error=None,
            fixture=True,
            usage=GatewayUsage(input_bytes=0, output_bytes=0, duration_ms=1, upstream_calls=1),
        )


async def main():
    settings = Settings()
    if settings.app_env != "test" or settings.gateway_mode != "fixture":
        raise SystemExit("Requires APP_ENV=test and GATEWAY_MODE=fixture")
    validate_test_database_url(settings.active_database_url)
    engine = get_engine(settings.active_database_url, "test")
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            admin, _ = await ensure_demo_user(
                db,
                username="html.bundle.admin",
                password="synthetic-html-pass-2026",
                role=UserRole.ADMIN,
                stage=None,
                grade=None,
                preferred_style=PreferredStyle.AUTO,
                interests=[],
                settings=settings,
            )
            with tempfile.TemporaryDirectory(prefix="k12-final-learning-") as temporary:
                package = Path(temporary)
                write_fixture(package)
                await import_package(db, load_package(package), dry_run=False)
            for stage in STAGES:
                viewer = ViewerScope(
                    stage=Stage(stage), grade=None, profile=content_profile_for(settings)
                )
                courses = await visible_courses(db, viewer)
                chapter = next(course for course in courses if course.slug == COURSE).chapters[0]
                previous = await db.scalar(
                    select(QuizDraft).where(
                        QuizDraft.chapter_id == chapter.chapter_id,
                        QuizDraft.owner_user_id == admin.id,
                        QuizDraft.validation_passed.is_(True),
                    )
                )
                if previous and previous.draft["questions"][0]["question_key"].startswith("final-"):
                    continue
                outcome = await create_quiz_draft_job(
                    db,
                    settings=settings,
                    gateway=FinalFixtureDesigner(),
                    requester=admin,
                    chapter_id=chapter.chapter_id,
                )
                if outcome.job.status != "SUCCEEDED" or not outcome.draft:
                    raise RuntimeError(f"Final fixture draft rejected: {outcome.job.error_code}")
            print(
                "Four synthetic lessons/drafts are ready. No answers submitted or scores created."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
