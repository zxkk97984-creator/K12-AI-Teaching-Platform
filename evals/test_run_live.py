from __future__ import annotations

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).with_name("run_live.py")
    spec = importlib.util.spec_from_file_location("t31_run_live", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_versioned_cases_build_frozen_valid_requests() -> None:
    live = _module()
    planned = live._validate_plan(live._load_cases())

    assert len(planned) == 16
    assert len({request["request_id"] for _, request in planned}) == 16
    assert len({request["lesson_session_id"] for _, request in planned}) == 16
    assert {case["stage"] for case, _ in planned} == {
        "PRIMARY_LOWER",
        "PRIMARY_UPPER",
        "JUNIOR",
        "SENIOR",
    }


def test_no_source_and_code_cases_are_fail_closed() -> None:
    live = _module()
    planned = {
        case["case_id"]: request
        for case, request in live._validate_plan(live._load_cases())
    }

    assert planned["SYN-PL-04"]["knowledge_context"] == []
    assert planned["SYN-PU-04"]["knowledge_context"] == []
    code = planned["SYN-JR-04"]
    assert code["operation"] == "CODE_FEEDBACK"
    assert code["code_feedback_facts"]["correctness_status"] == "FAILED"
    assert code["allowed_actions"] == []


def test_remote_ids_are_hashed_and_automated_checks_use_request_allowlists() -> None:
    live = _module()
    case, request = live._validate_plan(live._load_cases())[0]
    output = {
        "source_refs": [
            {
                "source_id": "synthetic-source-001",
                "revision": "synthetic-chapter-v1",
                "locator": "example:paragraph-1",
            }
        ],
        "action": None,
        "message_markdown": "synthetic",
    }

    checks = live._automated_checks(case, request, output)
    metadata = live._redacted_metadata(
        {"conversation_id": "opaque-conversation", "completion_id": "opaque-completion"}
    )

    assert all(checks.values())
    assert metadata is not None
    assert "conversation_id" not in metadata
    assert "completion_id" not in metadata
    assert len(metadata["conversation_id_sha256"]) == 64
    assert len(metadata["completion_id_sha256"]) == 64
