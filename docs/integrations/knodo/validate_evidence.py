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
    manifest = json.loads(
        (HERE / "source-snapshots/manifest.json").read_text(encoding="utf-8")
    )
    for name, item in manifest["files"].items():
        path = (
            HERE
            / "source-snapshots"
            / {
                "getting-started": "getting-started.html",
                "privacy": "privacy.html",
                "llms": "llms.txt",
                "llms-full": "llms-full.txt",
            }[name]
        )
        if not path.is_file():
            failures.append(f"missing snapshot {name}")
        elif digest(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            failures.append(f"snapshot drift {name}")
    evidence = json.loads(
        (HERE / "knodo-wire-evidence.json").read_text(encoding="utf-8")
    )
    expected_gates = {
        "G_API_CONTRACT",
        "G_LIVE_BUDGET",
        "G_AGENT_ISOLATION",
        "G_K12_TERMS",
        "G_HUMAN_CONTENT_REVIEW",
    }
    if set(evidence["gates"]) != expected_gates:
        failures.append("gate set mismatch")
    expected_status = {
        "G_API_CONTRACT": "PASS",
        "G_LIVE_BUDGET": "PASS",
        "G_AGENT_ISOLATION": "BLOCKED",
        "G_K12_TERMS": "BLOCKED",
        "G_HUMAN_CONTENT_REVIEW": "BLOCKED",
    }
    for gate, value in evidence["gates"].items():
        if value["status"] != expected_status[gate]:
            failures.append(f"{gate} status mismatch")
        if not value.get("reason"):
            failures.append(f"{gate} lacks status reason")
    if evidence["platform_permissions_verified"]:
        failures.append("platform permission isolation is not fully verified")
    if not evidence["bot_chat"]["tenant_verified"]:
        failures.append("live Bot Chat verification is missing")
    if evidence.get("actual_model_id") != "knodo/GLM-5.1":
        failures.append("actual live model mismatch")
    if evidence.get("actual_agent_os") != "CLAUDE_CODE":
        failures.append("actual live AgentOS mismatch")
    config = json.loads(
        (HERE / "tenant-config.user-reported.json").read_text(encoding="utf-8")
    )
    authorization = config["live_authorization"]
    if authorization["max_actual_requests"] != 20:
        failures.append("live request cap must remain 20")
    if any(
        authorization[key]
        for key in (
            "automatic_retry",
            "automatic_recharge",
            "plan_upgrade",
            "continue_after_exhaustion",
        )
    ):
        failures.append("live authorization forbids retry/recharge/upgrade/overage")
    t31_authorization = config.get("t31_authorization", {})
    if t31_authorization.get("user_stated_request_limit") != "NO_LIMIT_STATED":
        failures.append("T31 user authorization is not recorded")
    if t31_authorization.get("operational_cap_for_t31_local_v1") != 16:
        failures.append("T31 operational cap must equal the 16-case versioned eval set")
    if any(
        t31_authorization.get(key) is not False
        for key in ("automatic_retry", "automatic_recharge", "plan_upgrade")
    ):
        failures.append("T31 authorization must keep retry/recharge/upgrade disabled")
    credential = config["credential"]
    if credential.get("creator_account_role") != "ADMIN":
        failures.append("administrator PAT exception is not recorded")
    if credential.get("required_capability_categories") != ["AI / Chat 调用"]:
        failures.append("administrator PAT must require only AI / Chat capability")
    if not credential.get("revoke_after_live_evaluation"):
        failures.append(
            "administrator PAT must be revoked after the authorised live evaluation"
        )
    live = json.loads((HERE / "live-smoke.redacted.json").read_text(encoding="utf-8"))
    if not live.get("sequence_complete") or live.get("secrets_recorded") is not False:
        failures.append("live smoke is incomplete or secret handling is invalid")
    records = live.get("records")
    if not isinstance(records, list) or len(records) != 3:
        failures.append("live smoke must contain exactly three successful records")
    elif any(item.get("status") != "OK" for item in records if isinstance(item, dict)):
        failures.append("live smoke contains a non-success final record")
    ledger = HERE.parents[2] / "storage/private/knodo-request-budget.json"
    if ledger.is_file():
        budget = json.loads(ledger.read_text(encoding="utf-8"))
        if budget.get("reserved_requests", 21) > 20:
            failures.append("live request budget exceeded")
    t31_ledger = HERE.parents[2] / "storage/private/t31-request-budget.json"
    if t31_ledger.is_file():
        budget = json.loads(t31_ledger.read_text(encoding="utf-8"))
        if budget.get("authorized_max_requests") != 16:
            failures.append("T31 request budget cap mismatch")
        if budget.get("reserved_requests", 17) > 16:
            failures.append("T31 request budget exceeded")
    t31_live_path = HERE.parents[1] / "acceptance/T31-live-results.synthetic.json"
    t31_summary_path = HERE.parents[1] / "acceptance/T31-live-summary.json"
    if t31_live_path.is_file():
        t31_live = json.loads(t31_live_path.read_text(encoding="utf-8"))
        records = t31_live.get("records")
        if not t31_live.get("sequence_complete") or not isinstance(records, list):
            failures.append("T31 live evaluation is incomplete")
        elif len(records) != 16 or any(item.get("state") != "RECORDED" for item in records):
            failures.append("T31 live evaluation must contain 16 terminal records")
        if t31_live.get("secrets_recorded") is not False:
            failures.append("T31 live evidence secret handling is invalid")
        if not t31_summary_path.is_file():
            failures.append("T31 live summary is missing")
        else:
            t31_summary = json.loads(t31_summary_path.read_text(encoding="utf-8"))
            if t31_summary.get("source_evidence_sha256") != digest(t31_live_path):
                failures.append("T31 live summary does not match its source evidence")
            if t31_summary.get("human_review") != "NOT_RUN":
                failures.append("T31 human review must remain NOT_RUN until a person signs it")
    text = (HERE / "knodo-wire-evidence.json").read_text(encoding="utf-8")
    for forbidden in (
        "jvs_your_token_here",
        "Authorization: Bearer $JAVIS_AUTH_TOKEN",
        "knodo_site_access=",
    ):
        if forbidden in text:
            failures.append("possible credential-like value persisted")
    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1
    print(
        "PASS: official Bot Chat evidence and bounded user authorisation are consistent."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
