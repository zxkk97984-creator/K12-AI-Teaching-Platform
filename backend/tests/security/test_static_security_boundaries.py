from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_gates_requiring_external_isolation_and_terms_stay_blocked() -> None:
    progress = json.loads((ROOT / ".rebuild-kit/progress.json").read_text(encoding="utf-8"))
    assert progress["gates"]["G_AGENT_ISOLATION"]["status"] == "BLOCKED"
    assert progress["gates"]["G_K12_TERMS"]["status"] == "BLOCKED"
    assert progress["gates"]["G_HUMAN_CONTENT_REVIEW"]["status"] == "BLOCKED"


def test_frontend_source_contains_no_runtime_secret_names_or_private_keys() -> None:
    forbidden = ("KNODO_PAT", "APP_SESSION_SECRET", "BEGIN PRIVATE KEY", "/var/run/docker.sock")
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "frontend/src").rglob("*")
        if path.is_file()
    )
    assert all(marker not in source for marker in forbidden)


def test_api_and_runner_boundaries_do_not_mount_docker_socket() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    runner_docs = (ROOT / "docs/operations/RUNNER_T24.md").read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in compose
    assert "must not mount `/var/run/docker.sock`" in runner_docs
