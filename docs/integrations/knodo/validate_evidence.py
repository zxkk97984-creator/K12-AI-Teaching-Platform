#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    manifest = json.loads((HERE / "source-snapshots/manifest.json").read_text(encoding="utf-8"))
    for name, item in manifest["files"].items():
        path = HERE / "source-snapshots" / {
            "getting-started": "getting-started.html",
            "privacy": "privacy.html",
            "llms": "llms.txt",
            "llms-full": "llms-full.txt",
        }[name]
        if not path.is_file():
            failures.append(f"missing snapshot {name}")
        elif digest(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            failures.append(f"snapshot drift {name}")
    evidence = json.loads((HERE / "knodo-wire-evidence.json").read_text(encoding="utf-8"))
    expected_blocked = {"G_API_CONTRACT", "G_LIVE_BUDGET", "G_AGENT_ISOLATION", "G_K12_TERMS", "G_HUMAN_CONTENT_REVIEW"}
    if set(evidence["gates"]) != expected_blocked:
        failures.append("gate set mismatch")
    for gate, value in evidence["gates"].items():
        if value["status"] != "BLOCKED":
            failures.append(f"{gate} must remain BLOCKED without authorized live evidence")
        if not value.get("reason"):
            failures.append(f"{gate} lacks block reason")
    if evidence["platform_permissions_verified"] or evidence["bot_chat"]["tenant_verified"]:
        failures.append("public docs cannot set tenant verification")
    for key in ("first_request_redacted", "continue_request_redacted", "response_redacted", "stream_events_redacted", "actual_model_id", "actual_agent_os"):
        if evidence["bot_chat"].get(key, evidence.get(key)) is not None:
            failures.append(f"unverified field marked present: {key}")
    text = (HERE / "knodo-wire-evidence.json").read_text(encoding="utf-8")
    for forbidden in ("jvs_your_token_here", "Authorization: Bearer $JAVIS_AUTH_TOKEN", "knodo_site_access="):
        if forbidden in text:
            failures.append("possible credential-like value persisted")
    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1
    print("PASS: public Knodo snapshots match and all external gates remain BLOCKED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
