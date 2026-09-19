#!/usr/bin/env python3
"""Validate that read-only source repositories still match source_roots.json."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SNAPSHOT = PROJECT / "source_roots.json"


def run(*args: str, cwd: Path) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(path: Path) -> tuple[str, int, int]:
    rows: list[str] = []
    total = 0
    for file in sorted(item for item in path.rglob("*") if item.is_file() and not item.is_symlink()):
        size = file.stat().st_size
        total += size
        rows.append(f"{file.relative_to(path).as_posix()}\0{size}\0{sha256_file(file)}")
    return hashlib.sha256("\n".join(rows).encode()).hexdigest(), len(rows), total


def status_paths(root: Path) -> tuple[list[dict[str, str]], list[str]]:
    raw = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"], cwd=root)
    entries: list[dict[str, str]] = []
    untracked: list[str] = []
    tokens = raw.split(b"\0")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token:
            index += 1
            continue
        code = token[:2].decode()
        path = token[3:].decode("utf-8", "surrogateescape")
        entries.append({"code": code, "path": path})
        if code == "??":
            untracked.append(path)
        if code[0] in {"R", "C"} or code[1] in {"R", "C"}:
            index += 1
        index += 1
    return entries, untracked


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    failures: list[str] = []
    if str(PROJECT.resolve(strict=True)) != snapshot["target_realpath"]:
        failures.append("target realpath mismatch")
    for source in snapshot["sources"]:
        root = Path(source["realpath"])
        if not root.is_dir() or root.is_symlink():
            failures.append(f"{source['name']}: root missing or symlink")
            continue
        checks = {
            "head": run("git", "rev-parse", "HEAD", cwd=root),
            "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=root),
            "tree": run("git", "rev-parse", "HEAD^{tree}", cwd=root),
        }
        for key, actual in checks.items():
            if actual != source[key]:
                failures.append(f"{source['name']}: {key} changed: {source[key]} -> {actual}")
        entries, untracked_paths = status_paths(root)
        expected_entries = source["status_entries"]
        if entries != expected_entries:
            failures.append(f"{source['name']}: status entries changed")
        expected_untracked = {item["path"] for item in source["untracked_snapshot"]}
        if set(untracked_paths) != expected_untracked:
            failures.append(f"{source['name']}: untracked paths changed")
        for item in source["untracked_snapshot"]:
            path = root / item["path"].rstrip("/")
            if item["type"] == "file":
                if not path.is_file() or sha256_file(path) != item["sha256"]:
                    failures.append(f"{source['name']}: untracked file changed: {item['path']}")
            elif item["type"] == "directory":
                digest, count, total = tree_digest(path)
                if (digest, count, total) != (item["tree_sha256"], item["file_count"], item["total_bytes"]):
                    failures.append(f"{source['name']}: untracked directory changed: {item['path']}")
    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1
    print("PASS: target root and both source repositories match the T00 snapshot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
