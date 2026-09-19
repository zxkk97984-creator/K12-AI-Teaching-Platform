#!/usr/bin/env python3
"""Check the execution pack while allowing only progress.json to evolve."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
PACK = PROJECT / ".rebuild-kit"
CHECKSUM_FILE = PACK / "CHECKSUMS.sha256"
ALLOWED_CHANGE = "progress.json"


def main() -> int:
    failures: list[str] = []
    seen_progress = False
    for line in CHECKSUM_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split("  ", 1)
        target = PACK / name
        if name == ALLOWED_CHANGE:
            seen_progress = True
            continue
        if not target.is_file():
            failures.append(f"missing: {name}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            failures.append(f"unexpected change: {name}")
    if not seen_progress:
        failures.append("progress.json missing from checksum manifest")
    try:
        progress = json.loads((PACK / "progress.json").read_text(encoding="utf-8"))
        if progress.get("target_root") != str(PROJECT):
            failures.append("progress target_root mismatch")
    except Exception as exc:
        failures.append(f"progress.json invalid: {exc}")
    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1
    print("PASS: only progress.json differs from the execution pack checksum baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
