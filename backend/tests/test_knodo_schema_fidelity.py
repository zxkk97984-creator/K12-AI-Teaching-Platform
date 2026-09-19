"""T10/D1: the runtime models must accept exactly what the frozen schemas accept.

The gateway builds its Pydantic models from ``contracts/*.schema.json``. This
differential test pins that translation against the official validator for a
corpus of valid payloads and known mutations, and guards the keyword set so a
future schema change cannot slip in silently.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from app.integrations.knodo.schema_models import (
    METADATA_KEYWORDS,
    SUPPORTED_KEYWORDS,
    default_registry,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "contracts" / "examples"
SCHEMA_FILES = {
    "teaching-request": "teaching-request.schema.json",
    "teaching-response": "teaching-response.schema.json",
    "designer-request": "designer-request.schema.json",
    "quiz-draft": "quiz-draft.schema.json",
    "lesson-package-draft": "lesson-package-draft.schema.json",
}


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def schema_validator(name: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((ROOT / "contracts" / SCHEMA_FILES[name]).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def mutate(payload: dict, **changes) -> dict:
    mutated = copy.deepcopy(payload)
    mutated.update(changes)
    return mutated


def build_corpus() -> list[tuple[str, str, dict]]:
    teaching = load_example("teaching-request")
    teaching_response = load_example("teaching-response")
    designer_quiz = load_example("designer-request")
    designer_lesson = load_example("designer-package-request")
    quiz = load_example("quiz-draft")
    lesson = load_example("lesson-package-draft")

    corpus: list[tuple[str, str, dict]] = [
        ("teaching-request", "valid", teaching),
        (
            "teaching-request",
            "null grade",
            mutate(teaching, learner={**teaching["learner"], "grade": None}),
        ),
        (
            "teaching-request",
            "grade 0",
            mutate(teaching, learner={**teaching["learner"], "grade": 0}),
        ),
        (
            "teaching-request",
            "grade 13",
            mutate(teaching, learner={**teaching["learner"], "grade": 13}),
        ),
        (
            "teaching-request",
            "bool grade",
            mutate(teaching, learner={**teaching["learner"], "grade": True}),
        ),
        (
            "teaching-request",
            "string grade",
            mutate(teaching, learner={**teaching["learner"], "grade": "5"}),
        ),
        ("teaching-request", "extra root property", mutate(teaching, undeclared="x")),
        (
            "teaching-request",
            "missing learner",
            {key: value for key, value in teaching.items() if key != "learner"},
        ),
        ("teaching-request", "unknown event", mutate(teaching, event="TELEPORT")),
        (
            "teaching-request",
            "unknown action",
            mutate(teaching, allowed_actions=["DELETE_EVERYTHING"]),
        ),
        (
            "teaching-request",
            "quiz question budget",
            mutate(teaching, limits={**teaching["limits"], "max_quiz_questions": 6}),
        ),
        (
            "teaching-request",
            "duplicate objective ids",
            mutate(
                teaching,
                chapter={**teaching["chapter"], "objective_ids": ["dup", "dup"]},
            ),
        ),
        ("teaching-request", "request id too long", mutate(teaching, request_id="r" * 161)),
        ("teaching-request", "student input too long", mutate(teaching, student_input="s" * 8001)),
        ("teaching-request", "code facts null", mutate(teaching, code_feedback_facts=None)),
        (
            "teaching-request",
            "bool passed cases",
            mutate(
                teaching,
                code_feedback_facts={
                    "run_id": "r",
                    "task_id": "t",
                    "code_hash": "h",
                    "code_excerpt": "",
                    "execution_status": "SUCCEEDED",
                    "correctness_status": "PASSED",
                    "stdout_excerpt": "",
                    "error_excerpt": "",
                    "passed_cases": True,
                    "total_cases": 1,
                },
            ),
        ),
        ("teaching-response", "valid", teaching_response),
        ("teaching-response", "null action", mutate(teaching_response, action=None)),
        (
            "teaching-response",
            "offer quiz without difficulty",
            mutate(
                teaching_response,
                action={
                    "type": "OFFER_QUIZ",
                    "objective_ids": ["obj-1"],
                    "question_count": 1,
                },
            ),
        ),
        ("teaching-response", "unknown warning", mutate(teaching_response, warnings=["MYSTERY"])),
        (
            "teaching-response",
            "duplicate warnings",
            mutate(teaching_response, warnings=["NEEDS_HUMAN_REVIEW", "NEEDS_HUMAN_REVIEW"]),
        ),
        (
            "teaching-response",
            "too many source refs",
            mutate(
                teaching_response,
                source_refs=[
                    {"source_id": f"s{index}", "revision": "r1", "locator": "l"}
                    for index in range(9)
                ],
            ),
        ),
        ("teaching-response", "empty message", mutate(teaching_response, message_markdown="")),
        (
            "teaching-response",
            "tampered version",
            mutate(teaching_response, schema_version="k12.teaching.response.v2"),
        ),
        ("designer-request", "valid quiz", designer_quiz),
        ("designer-request", "valid lesson", designer_lesson),
        (
            "designer-request",
            "quiz branch with lesson spec",
            mutate(designer_quiz, lesson_spec=designer_lesson["lesson_spec"]),
        ),
        (
            "designer-request",
            "lesson branch with quiz spec",
            mutate(designer_lesson, quiz_spec=designer_quiz["quiz_spec"]),
        ),
        ("designer-request", "extra property", mutate(designer_quiz, undeclared=1)),
        ("designer-request", "unknown stage", mutate(designer_quiz, stage="KINDERGARTEN")),
        (
            "designer-request",
            "empty objective ids",
            mutate(designer_quiz, objective_ids=[]),
        ),
        (
            "designer-request",
            "duplicate objective ids",
            mutate(designer_quiz, objective_ids=["dup", "dup"]),
        ),
        ("quiz-draft", "valid", quiz),
        ("quiz-draft", "no questions", mutate(quiz, questions=[])),
        ("quiz-draft", "unknown difficulty", mutate(quiz, difficulty="IMPOSSIBLE")),
        (
            "quiz-draft",
            "too many warnings",
            mutate(quiz, warnings=[f"w{index}" for index in range(9)]),
        ),
        (
            "quiz-draft",
            "question missing answer",
            mutate(
                quiz,
                questions=[
                    {
                        key: value
                        for key, value in quiz["questions"][0].items()
                        if key != "correct_answer"
                    }
                ],
            ),
        ),
        (
            "quiz-draft",
            "question extra property",
            mutate(quiz, questions=[{**quiz["questions"][0], "undeclared": True}]),
        ),
        ("lesson-package-draft", "valid", lesson),
        ("lesson-package-draft", "empty title", mutate(lesson, title="")),
        (
            "lesson-package-draft",
            "too many warnings",
            mutate(lesson, warnings=[f"w{index}" for index in range(13)]),
        ),
        ("lesson-package-draft", "extra property", mutate(lesson, undeclared=1)),
        (
            "lesson-package-draft",
            "source ref missing locator",
            mutate(lesson, source_refs=[{"source_id": "s", "revision": "r1"}]),
        ),
    ]
    return corpus


@pytest.mark.parametrize(
    "schema_name,label,payload", build_corpus(), ids=lambda value: str(value)[:60]
)
def test_runtime_models_match_the_frozen_schemas(
    schema_name: str, label: str, payload: dict
) -> None:
    registry = default_registry()
    expected = schema_validator(schema_name).is_valid(payload)
    problems = registry.validate_schema(schema_name, payload)
    assert (not problems) == expected, (
        f"{schema_name}/{label}: model={problems} schema_ok={expected}"
    )


def test_every_schema_keyword_is_supported() -> None:
    seen: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties":
                    for subschema in value.values():
                        walk(subschema)
                    seen.add(key)
                    continue
                seen.add(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for filename in SCHEMA_FILES.values():
        walk(json.loads((ROOT / "contracts" / filename).read_text(encoding="utf-8")))

    # Field names inside "properties" are legitimately arbitrary; everything else
    # must be a keyword the runtime builder either honours or rejects loudly.
    unknown = seen - SUPPORTED_KEYWORDS - METADATA_KEYWORDS
    assert not unknown, f"unsupported keywords would fail loudly at import: {sorted(unknown)}"
