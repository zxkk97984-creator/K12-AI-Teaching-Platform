from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.modules.codelab.contracts import (
    load_catalog,
    load_catalog_metadata,
    parse_task_document,
    public_task_view,
)
from app.modules.codelab.trusted import validate_trusted_manifest


def test_catalog_has_twelve_stage_bound_tasks_and_real_trusted_digests() -> None:
    loaded = load_catalog()
    assert [task.task_id for _, task in loaded] == [
        "balanced-brackets",
        "binary-search",
        "climbing-stairs",
        "even-sum",
        "list-summary",
        "odd-even",
        "palindrome-check",
        "prediction-accuracy",
        "range-sum",
        "sort-unique",
        "temperature-converter",
        "word-frequency",
    ]
    stages = {
        task.chapter_binding.stage
        for _, task in loaded
        if task.task_id in {"odd-even", "even-sum", "palindrome-check", "word-frequency"}
    }
    assert stages == {"JUNIOR"}
    assert {
        task.chapter_binding.stage
        for _, task in loaded
        if task.task_id
        in {
            "prediction-accuracy",
            "sort-unique",
            "balanced-brackets",
            "range-sum",
            "climbing-stairs",
        }
    } == {"SENIOR"}
    for _, task in loaded:
        assert task.status == "DRAFT"
        assert task.review_status == "UNREVIEWED"
        assert task.is_test_fixture is (task.source.source_kind == "SYNTHETIC_FIXTURE")
        validate_trusted_manifest(
            task.task_id,
            expected_count=task.test_manifest.hidden_case_count,
            expected_sha256=task.test_manifest.hidden_cases_sha256,
        )

    assert len(load_catalog_metadata()) == 12


def test_public_task_view_excludes_reference_and_hidden_data() -> None:
    for _, task in load_catalog():
        dumped = json.dumps(public_task_view(task), ensure_ascii=False, sort_keys=True)
        assert "reference_solution" not in dumped
        assert '"hidden_cases_sha256"' not in dumped
        assert '"tests"' not in dumped
        assert '"test_groups"' not in dumped
        assert '"public_test_groups"' in dumped


def test_secret_fields_are_rejected_even_if_added_to_manifest() -> None:
    payload = load_catalog()[0][1].model_dump(mode="json")
    payload["reference_solution"] = "def fake(): return 1"
    with pytest.raises(ValueError, match="reference_solution"):
        parse_task_document(payload)


def test_old_rubric_is_not_silently_promoted_to_ai_authority() -> None:
    for _, task in load_catalog():
        assert task.rubric.score_scale == 70
        assert task.rubric.ai_feedback_non_authoritative is True


def test_synthetic_source_hashes_and_test_manifests_are_bound_to_real_files() -> None:
    for path, task in load_catalog():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if task.source.source_kind == "SYNTHETIC_FIXTURE":
            assert task.source.source_path.endswith(path.name)
            assert task.source.source_sha256
            assert len(task.source.reference_solution_sha256) == 64
            assert (
                len(
                    __import__(
                        "app.modules.codelab.trusted", fromlist=["trusted_cases"]
                    ).trusted_cases(task.task_id)
                )
                == 8
            )
            assert raw["is_test_fixture"] is True


def test_json_schema_accepts_every_catalog_definition() -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "runner/contracts/code-task.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema)
    for path, _ in load_catalog():
        errors = sorted(
            validator.iter_errors(json.loads(path.read_text(encoding="utf-8"))), key=str
        )
        assert errors == [], [error.message for error in errors]
