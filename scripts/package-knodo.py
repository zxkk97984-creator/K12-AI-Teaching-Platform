#!/usr/bin/env python3
"""Reproducible packaging and verification for the Knodo delivery assets.

Subcommands
-----------
build-bundles  Regenerate the teacher-visible classroom bundle from the
               immutable curriculum release mirror (fixtures only).
build          Build the release ZIPs, per-entry SHA256 manifest, deployment
               manifest (PACKAGED / NOT_DEPLOYED) and release SHA256SUMS.
verify         Verify a built release: ZIP safety, hashes, schema byte
               equality with the frozen contracts, answer/key separation,
               bundle scans and deployment status.
scan           Scan the package tree for secrets, keys and absolute paths.
selftest       Negative cases: tampered entry, traversal entry, absolute-path
               entry, injected secret and modified schema must all be caught.

Only the Python standard library is used so the script runs without the
backend virtualenv. Nothing here calls Knodo or any network service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "platform" / "knodo"
CONTRACTS = ROOT / "contracts"
STAGE_POLICY = PACKAGE / "stage-policy.json"
CURRICULUM_MIRROR = ROOT / "curriculum" / "releases"
DEFAULT_RELEASE_ID = "knodo-assets-1.0.0"

SKILLS = ("k12-teaching-core", "k12-assessment-author", "k12-content-author")
SKILL_SCHEMAS = {
    "k12-teaching-core": (
        "teaching-request.schema.json",
        "teaching-response.schema.json",
    ),
    "k12-assessment-author": ("designer-request.schema.json", "quiz-draft.schema.json"),
    "k12-content-author": (
        "designer-request.schema.json",
        "lesson-package-draft.schema.json",
    ),
}
FROZEN_CONTRACT_VERSION = json.loads(
    (CONTRACTS / "version.json").read_text(encoding="utf-8")
)["contract_version"]

ZIP_DATE = (1980, 1, 1, 0, 0, 0)
ZIP_MODE = 0o100644

# Structure-level rules for anything a student or the Tutor may read.
FORBIDDEN_KEYS = {
    "answer",
    "answers",
    "answer_key",
    "answer_keys",
    "correct_option",
    "solution",
    "reference_solution",
    "hidden_test",
    "hidden_tests",
    "expected_output",
    "reviewer",
    "review_comment",
    "student_id",
    "user_id",
    "email",
    "phone",
    "password",
    "token",
    "pat",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"://[^/\s:]+:[^/\s@]+@"),
)
ABSOLUTE_PATH_PATTERNS = (
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/tmp/[A-Za-z0-9._-]+"),
    re.compile(r"/var/[A-Za-z0-9._-]+/"),
    re.compile(r"\b[A-Za-z]:\\\\"),
)
TEXT_SUFFIXES = {".md", ".json", ".txt", ".py", ".sh", ".yaml", ".yml"}


class CheckFailed(RuntimeError):
    """A verification rule failed."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


# --------------------------------------------------------------------------- #
# Classroom bundle (Teacher-visible only)
# --------------------------------------------------------------------------- #

CLASSROOM_README = """# 课堂知识包（classroom bundle）

本目录是 Tutor 可读取的**受控课堂知识包**。构建者是 `scripts/package-knodo.py build-bundles`，
数据来源是 `curriculum/releases/` 下的不可变修订镜像。

规则：

1. 只包含 Teacher 可见内容：章节标题、学习目标、知识点说明、正文块与来源登记。
2. **不包含**标准答案、参考解、隐藏测试、未审题库、原始学生档案或任何密钥。
3. 当前包是**测试内容包**（`bundle_kind=TEST_FIXTURE_BUNDLE`），界面与说明必须保持
   “测试内容，未作人工教学审校”的标识，不得用于真实学生。
4. 正式知识包要求课程修订处于 `HUMAN_APPROVED + PUBLISHED`；文件系统打包器不产出正式包，
   正式包由应用在 T10/T12 绑定真实章节 ID 后导出。
"""


def build_classroom_item(snapshot: dict) -> dict:
    chapter = snapshot["chapter"]
    course = snapshot["course"]
    is_fixture = bool(snapshot.get("is_test_fixture"))
    return {
        "schema_version": "k12.knodo.classroom-item.v1",
        "source_id": f"chapter:{course['slug']}/{chapter['slug']}",
        "binding": {
            "chapter_uuid": None,
            "resolved_by": "local_app",
            "note": "文件系统镜像不含数据库 UUID；由本地应用在部署时绑定。",
        },
        "course": {
            "slug": course["slug"],
            "title": course["title"],
            "topic": course["topic"],
        },
        "chapter": {
            "slug": chapter["slug"],
            "title": chapter["title"],
            "revision": chapter["revision"],
            "stage": chapter["stage"],
            "grade_min": chapter["grade_min"],
            "grade_max": chapter["grade_max"],
            "objectives": list(chapter["objectives"]),
            "knowledge_points": [
                {
                    "slug": item["slug"],
                    "name": item["name"],
                    "topic": item["topic"],
                    "description": item["description"],
                }
                for item in chapter["knowledge_points"]
            ],
            "blocks": list(chapter["blocks"]),
        },
        "provenance": {
            "release_key": snapshot["release_key"],
            "release_manifest_hash": snapshot["manifest_hash"],
            "source_kind": snapshot["source_kind"],
            "is_test_fixture": is_fixture,
            "source_commit": chapter["source"].get("source_commit"),
            "source_path": chapter["source"].get("source_path"),
            "license_code": chapter["license_code"],
        },
        "review": {
            "review_status": "UNREVIEWED",
            "publication_status": "DRAFT",
            "human_reviewed": False,
        },
        "usage": {
            "for_real_students": False,
            "notice": "测试内容，未作人工教学审校",
        },
        "content_hash": snapshot["content_hash"],
    }


def build_bundles(release_id: str = DEFAULT_RELEASE_ID) -> dict:
    classroom = PACKAGE / "bundles" / "classroom"
    content_dir = classroom / "content"
    if content_dir.exists():
        shutil.rmtree(content_dir)
    content_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    excluded: list[dict] = []
    for snapshot_path in sorted(CURRICULUM_MIRROR.glob("*/*/*.json")):
        snapshot = read_json(snapshot_path)
        if snapshot.get("schema_version") != "k12.content.revision-snapshot.v1":
            continue
        if not snapshot.get("is_test_fixture"):
            excluded.append(
                {
                    "release_key": snapshot["release_key"],
                    "chapter": f"{snapshot['course']['slug']}/{snapshot['chapter']['slug']}",
                    "reason": "非测试内容且未处于 HUMAN_APPROVED+PUBLISHED；文件系统打包器不产出正式包",
                }
            )
            continue
        item = build_classroom_item(snapshot)
        target = (
            content_dir
            / item["course"]["slug"]
            / f"{item['chapter']['slug']}-r{item['chapter']['revision']}.json"
        )
        write_json(target, item)
        items.append(
            {
                "source_id": item["source_id"],
                "revision": item["chapter"]["revision"],
                "stage": item["chapter"]["stage"],
                "sha256": sha256_file(target),
                "path": rel(target),
                "is_test_fixture": True,
            }
        )

    classroom_manifest = {
        "schema_version": "k12.knodo.classroom-bundle.v1",
        "bundle_kind": "TEST_FIXTURE_BUNDLE",
        "for_real_students": False,
        "notice": "测试内容，未作人工教学审校",
        "release_id": release_id,
        "items": items,
        "contains_answer_material": False,
    }
    write_json(classroom / "manifest.json", classroom_manifest)
    (classroom / "README.md").write_text(CLASSROOM_README, encoding="utf-8")

    package_manifest = {
        "schema_version": "k12.knodo.bundle-manifest.v1",
        "release_id": release_id,
        "bundle_kind": "TEST_FIXTURE_BUNDLE",
        "for_real_students": False,
        "formal_bundle_status": "NOT_AVAILABLE",
        "formal_bundle_requirement": (
            "需要 HUMAN_APPROVED + PUBLISHED 的课程修订；当前仓库没有通过真实人工审校的内容"
        ),
        "tutor_visible": items,
        "designer_private": {
            "boundary_doc": "designer-private/BOUNDARY.md",
            "manifest": "designer-private/boundary-manifest.json",
            "included_items": [],
            "shipped_as_zip": False,
            "note": "答案/解析/隐藏测试/参考解不进入任何随包发布目录",
        },
        "separation": {
            "tutor_visible_count": len(items),
            "designer_private_count": 0,
            "answers_in_tutor_bundle": False,
        },
        "excluded_sources": excluded,
    }
    write_json(PACKAGE / "bundles" / "manifest.json", package_manifest)
    return package_manifest


# --------------------------------------------------------------------------- #
# ZIP helpers
# --------------------------------------------------------------------------- #


def build_zip(zip_path: Path, entries: list[tuple[Path, str]]) -> None:
    """Deterministic ZIP: fixed order, fixed timestamps, fixed compression."""

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for source, arcname in sorted(entries, key=lambda item: item[1]):
            info = zipfile.ZipInfo(arcname, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = ZIP_MODE << 16
            archive.writestr(
                info,
                source.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def zip_safety_problems(archive: zipfile.ZipFile) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for info in archive.infolist():
        name = info.filename
        if name in seen:
            problems.append(f"duplicate entry: {name}")
        seen.add(name)
        if name.startswith("/") or name.startswith("\\"):
            problems.append(f"absolute entry: {name}")
        if re.match(r"^[A-Za-z]:", name):
            problems.append(f"drive-letter entry: {name}")
        if "\\" in name:
            problems.append(f"backslash entry: {name}")
        parts = [part for part in name.split("/") if part not in ("", ".")]
        if ".." in parts:
            problems.append(f"traversal entry: {name}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            problems.append(f"symlink entry: {name}")
    return problems


def zip_entry_records(zip_path: Path) -> list[dict]:
    with zipfile.ZipFile(zip_path) as archive:
        problems = zip_safety_problems(archive)
        if problems:
            raise CheckFailed(f"{zip_path.name}: unsafe ZIP entries: {problems}")
        return [
            {
                "name": info.filename,
                "sha256": sha256_bytes(archive.read(info)),
                "bytes": info.file_size,
            }
            for info in sorted(archive.infolist(), key=lambda item: item.filename)
        ]


def assert_zip_entries_match(
    zip_path: Path, expected: list[dict], *, where: str
) -> None:
    actual = zip_entry_records(zip_path)
    if actual != sorted(expected, key=lambda item: item["name"]):
        raise CheckFailed(f"{where}: ZIP entries differ from the release manifest")


# --------------------------------------------------------------------------- #
# Release build
# --------------------------------------------------------------------------- #


def artifact_specs() -> list[dict]:
    specs: list[dict] = [
        {
            "name": "memory-v1.zip",
            "root": PACKAGE / "memory" / "v1",
            "prefix": "memory/v1",
            "kind": "bot-config",
        },
        {
            "name": "tutor-v1.zip",
            "root": PACKAGE / "tutor" / "v1",
            "prefix": "tutor/v1",
            "kind": "bot_system_prompt",
        },
        {
            "name": "designer-v1.zip",
            "root": PACKAGE / "designer" / "v1",
            "prefix": "designer/v1",
            "kind": "bot_system_prompt",
        },
        {
            "name": "bundles-classroom.zip",
            "root": PACKAGE / "bundles" / "classroom",
            "prefix": "",
            "kind": "knowledge_bundle",
        },
    ]
    for skill in SKILLS:
        specs.append(
            {
                "name": f"skill-{skill}.zip",
                "root": PACKAGE / "skills" / skill,
                "prefix": "",
                "kind": "skill",
            }
        )
        specs.append(
            {
                "name": f"plugin-{skill}.zip",
                "root": PACKAGE / "skills" / skill,
                "prefix": f"skills/{skill}",
                "kind": "plugin",
            }
        )
    return specs


def collect_entries(root: Path, prefix: str) -> list[tuple[Path, str]]:
    entries: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        arcname = path.relative_to(root).as_posix()
        entries.append((path, f"{prefix}/{arcname}" if prefix else arcname))
    return entries


def build_artifact(zip_path: Path, spec: dict) -> None:
    entries = collect_entries(spec["root"], spec["prefix"])
    if spec["kind"] != "plugin":
        build_zip(zip_path, entries)
        return
    problems = verify_skill_tree(spec["root"], where=spec["name"])
    if problems:
        raise CheckFailed("; ".join(problems))
    skill = spec["root"].name
    description = (
        re.search(
            r"^description:\s*(.+)$",
            (spec["root"] / "SKILL.md").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        .group(1)
        .strip()
    )
    metadata = {
        "name": skill,
        "version": read_json(PACKAGE / "VERSION.json")["package_version"],
        "description": description,
        "author": {"name": "霜铃 K12 项目"},
        "skills": "./skills/",
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_json = root / "plugin.json"
        write_json(plugin_json, metadata)
        # JSON scalar quoting is valid YAML and avoids another packaging dependency.
        plugin_yaml = root / "plugin.yaml"
        plugin_yaml.write_text(
            "\n".join(
                f"{key}: {json.dumps(metadata[key], ensure_ascii=False)}"
                for key in ("name", "version", "description", "author")
            )
            + "\n",
            encoding="utf-8",
        )
        build_zip(
            zip_path,
            entries
            + [
                (plugin_json, ".claude-plugin/plugin.json"),
                (plugin_yaml, "plugin.yaml"),
            ],
        )


def verify_plugin_archive(zip_path: Path, skill: str) -> None:
    """Catch upload-format errors before handing a Plugin ZIP to Knodo."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            metadata = json.loads(archive.read(".claude-plugin/plugin.json"))
            if not isinstance(metadata, dict) or metadata.get("name") != skill:
                raise CheckFailed(f"{zip_path.name}: plugin name mismatch")
            author = metadata.get("author")
            if (
                not isinstance(author, dict)
                or not isinstance(author.get("name"), str)
                or not author["name"].strip()
            ):
                raise CheckFailed(
                    f"{zip_path.name}: plugin author must be an object with a name"
                )
            if metadata.get("skills") != "./skills/":
                raise CheckFailed(f"{zip_path.name}: plugin skills directory mismatch")
            if f"skills/{skill}/SKILL.md" not in archive.namelist():
                raise CheckFailed(f"{zip_path.name}: nested SKILL.md missing")
    except (KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise CheckFailed(f"{zip_path.name}: invalid Plugin manifest") from exc


def deployment_manifest(release_id: str, hashes: dict[str, str]) -> dict:
    return {
        "schema_version": "k12.knodo.deployment-manifest.v1",
        "release_id": release_id,
        "artifact_status": "PACKAGED",
        "deployment_status": "NOT_DEPLOYED",
        "deployment_verified": False,
        "bot_roles": {
            **{
                role: {
                    "bot_id": None,
                    "workspace_id": None,
                    "operations": ["TEACH_TURN", "CODE_FEEDBACK"],
                    "skills": ["k12-teaching-core"],
                    "system_prompt": f"tutor/v1/stages/{role}.md",
                    "stages": stages,
                    "response_mode": "STREAMING_STRUCTURED",
                    "packaged_config_hash": hashes.get("tutor-v1.zip"),
                    "packaged_knowledge_bundle_hash": hashes.get(
                        "bundles-classroom.zip"
                    ),
                    "deployed_config_hash": None,
                    "deployment_verified": False,
                }
                for role, stages in (
                    ("primary", ["PRIMARY_LOWER", "PRIMARY_UPPER"]),
                    ("junior", ["JUNIOR"]),
                    ("senior", ["SENIOR"]),
                )
            },
            "designer": {
                "bot_id": None,
                "workspace_id": None,
                "operations": ["QUIZ_DRAFT", "LESSON_PACKAGE_DRAFT"],
                "skills": ["k12-assessment-author", "k12-content-author"],
                "system_prompt": "designer/v1/system-prompt.md",
                "response_mode": "BUFFERED_STRUCTURED",
                "live_operations": ["QUIZ_DRAFT"],
                "packaged_config_hash": hashes.get("designer-v1.zip"),
                "packaged_knowledge_bundle_hash": None,
                "deployed_config_hash": None,
                "deployment_verified": False,
            },
            "memory": {
                "bot_id": None,
                "workspace_id": None,
                "operations": ["MEMORY_EXTRACT"],
                "skills": [],
                "system_prompt": "memory/v1/system-prompt.md",
                "response_mode": "BUFFERED_STRUCTURED",
                "packaged_config_hash": hashes.get("memory-v1.zip"),
                "deployed_config_hash": None,
                "deployment_verified": False,
            },
        },
        "agent_os": None,
        "runtime_model_id": None,
        "native_subagents_required": False,
        "actual_permissions_reviewed": False,
        "fixture_is_not_live": True,
        "not_deployed_reason": "此清单仅描述可复现本地资产，不记录个人部署凭据或远端验收结果；实际绑定以数据库注册表及实时核验为准。",
        "manual_steps_ref": "docs/integrations/knodo/DEPLOYMENT_GUIDE.md",
        "boundaries_ref": "docs/integrations/knodo/ASSET_BOUNDARIES.md",
    }


def build_release(release_id: str) -> dict:
    bundle_manifest = build_bundles(release_id)
    release_dir = PACKAGE / "releases" / release_id
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict] = []
    hashes: dict[str, str] = {}
    for spec in artifact_specs():
        zip_path = release_dir / spec["name"]
        build_artifact(zip_path, spec)
        hashes[spec["name"]] = sha256_file(zip_path)
        artifacts.append(
            {
                "name": spec["name"],
                "kind": spec["kind"],
                "source_path": rel(spec["root"]),
                "sha256": hashes[spec["name"]],
                "bytes": zip_path.stat().st_size,
                "entries": zip_entry_records(zip_path),
            }
        )

    manifest = deployment_manifest(release_id, hashes)
    canonical_manifest = PACKAGE / "deployment-manifest.json"
    write_json(canonical_manifest, manifest)
    shutil.copyfile(canonical_manifest, release_dir / "deployment-manifest.json")

    version = read_json(PACKAGE / "VERSION.json")
    if version["contract_version"] != FROZEN_CONTRACT_VERSION:
        raise CheckFailed(
            "VERSION.json contract_version differs from contracts/version.json"
        )

    release_manifest = {
        "schema_version": "k12.knodo.release-manifest.v1",
        "release_id": release_id,
        "package_version": version["package_version"],
        "contract_version": version["contract_version"],
        "artifacts": artifacts,
        "deployment_manifest": {
            "path": "deployment-manifest.json",
            "sha256": sha256_file(release_dir / "deployment-manifest.json"),
        },
        "bundle_summary": {
            "bundle_kind": bundle_manifest["bundle_kind"],
            "for_real_students": bundle_manifest["for_real_students"],
            "tutor_visible_count": bundle_manifest["separation"]["tutor_visible_count"],
            "designer_private_count": bundle_manifest["separation"][
                "designer_private_count"
            ],
            "answers_in_tutor_bundle": bundle_manifest["separation"][
                "answers_in_tutor_bundle"
            ],
            "excluded_sources": bundle_manifest["excluded_sources"],
        },
        "rules": {
            "skill_names": list(SKILLS),
            "native_subagents_required": False,
            "zip_reproducible": True,
            "no_secrets": True,
            "no_absolute_paths_in_zip": True,
            "schema_byte_equal_to_frozen_contracts": True,
        },
    }
    write_json(release_dir / "release-manifest.json", release_manifest)

    sums = []
    for path in sorted(release_dir.iterdir()):
        if path.name == "SHA256SUMS" or not path.is_file():
            continue
        sums.append(f"{sha256_file(path)}  {path.name}")
    (release_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return release_manifest


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def scan_text(value: str, *, where: str) -> list[str]:
    problems: list[str] = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            problems.append(f"{where}: secret-like pattern {pattern.pattern!r}")
    for pattern in ABSOLUTE_PATH_PATTERNS:
        if pattern.search(value):
            problems.append(f"{where}: absolute path pattern {pattern.pattern!r}")
    return problems


def walk_keys(node, *, where: str) -> list[str]:
    problems: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in FORBIDDEN_KEYS:
                problems.append(f"{where}: forbidden key {key!r}")
            problems.extend(walk_keys(value, where=f"{where}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            problems.extend(walk_keys(item, where=f"{where}[{index}]"))
    return problems


def verify_skill_tree(skill_dir: Path, *, where: str) -> list[str]:
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{where}: SKILL.md missing"]
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        problems.append(f"{where}: SKILL.md frontmatter missing")
        return problems
    frontmatter = match.group(1)
    name_match = re.search(r"^name:\s*(\S+)\s*$", frontmatter, re.MULTILINE)
    description_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    if not name_match:
        problems.append(f"{where}: frontmatter missing name")
    elif name_match.group(1) != skill_dir.name:
        problems.append(f"{where}: frontmatter name != directory name")
    if not description_match or not description_match.group(1).strip():
        problems.append(f"{where}: frontmatter description empty")
    for referenced in sorted(set(re.findall(r"references/[A-Za-z0-9._-]+", text))):
        if not (skill_dir / referenced).is_file():
            problems.append(f"{where}: referenced file missing: {referenced}")
    for schema in SKILL_SCHEMAS[skill_dir.name]:
        local = skill_dir / "references" / schema
        frozen = CONTRACTS / schema
        if not local.is_file():
            problems.append(f"{where}: schema missing: {schema}")
        elif local.read_bytes() != frozen.read_bytes():
            problems.append(f"{where}: schema differs from frozen contract: {schema}")
    stage_policy = skill_dir / "references" / "stage-policy.json"
    source_policy = STAGE_POLICY
    if not source_policy.is_file():
        problems.append(f"{where}: canonical stage-policy.json missing")
    elif stage_policy.is_file():
        if stage_policy.read_bytes() != source_policy.read_bytes():
            problems.append(f"{where}: stage-policy.json differs from source asset")
    return problems


def verify_quiz_sample(sample: Path, *, where: str) -> list[str]:
    """QA16: the draft may carry answers, the student projection must not."""

    problems: list[str] = []
    frozen_example = CONTRACTS / "examples" / "quiz-draft.json"
    if frozen_example.is_file() and sample.read_bytes() != frozen_example.read_bytes():
        problems.append(f"{where}: sample differs from frozen contract example")
    payload = read_json(sample)
    questions = payload.get("questions") or []
    if not questions:
        problems.append(f"{where}: sample has no questions")
    for index, question in enumerate(questions):
        keys = [option.get("key") for option in (question.get("options") or [])]
        if len(set(keys)) != len(keys):
            problems.append(f"{where}: question {index} has duplicate option keys")
        answer = question.get("correct_answer")
        if answer is None:
            problems.append(f"{where}: question {index} has no private answer field")
        if question.get("type") == "SINGLE_CHOICE" and answer not in keys:
            problems.append(
                f"{where}: question {index} answer is not one of the options"
            )

        # The student-visible projection is what the app may send to a student.
        projection = {
            "stem": question.get("stem"),
            "options": question.get("options"),
            "hints": question.get("hints"),
            "type": question.get("type"),
            "objective_id": question.get("objective_id"),
            "source_refs": question.get("source_refs"),
        }
        projection_text = json.dumps(projection, ensure_ascii=False)
        if question.get("correct_answer") and str(
            question["correct_answer"]
        ) in json.dumps(question.get("options"), ensure_ascii=False):
            pass  # option keys are legitimately visible; only the private field must not be
        problems.extend(walk_keys(projection, where=f"{where}#q{index}"))
        explanation = question.get("explanation")
        if explanation and explanation in projection_text:
            problems.append(
                f"{where}: question {index} leaks the explanation into the projection"
            )
        if "correct_answer" in projection_text or "explanation" in projection_text:
            problems.append(
                f"{where}: question {index} projection carries private keys"
            )

    problems.extend(scan_text(json.dumps(payload, ensure_ascii=False), where=where))
    return problems


def verify_release(release_id: str, *, check_reproducible: bool = True) -> list[str]:
    problems: list[str] = []
    release_dir = PACKAGE / "releases" / release_id
    if not release_dir.is_dir():
        return [f"release directory missing: {rel(release_dir)}"]
    manifest_path = release_dir / "release-manifest.json"
    if not manifest_path.is_file():
        return [f"release manifest missing: {rel(manifest_path)}"]
    manifest = read_json(manifest_path)

    if manifest["contract_version"] != FROZEN_CONTRACT_VERSION:
        problems.append(
            "release manifest contract_version differs from frozen contracts"
        )

    # SHA256SUMS covers every file in the release directory
    sums_path = release_dir / "SHA256SUMS"
    if not sums_path.is_file():
        problems.append("SHA256SUMS missing")
    else:
        listed = {}
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, name = line.split("  ", 1)
            listed[name] = digest
        for path in sorted(release_dir.iterdir()):
            if path.name == "SHA256SUMS" or not path.is_file():
                continue
            actual = sha256_file(path)
            if listed.get(path.name) != actual:
                problems.append(f"SHA256SUMS mismatch for {path.name}")
        for name in listed:
            if not (release_dir / name).is_file():
                problems.append(f"SHA256SUMS lists missing file {name}")

    # Artifacts: hashes, entries and extraction
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for artifact in manifest["artifacts"]:
            zip_path = release_dir / artifact["name"]
            if not zip_path.is_file():
                problems.append(f"artifact missing: {artifact['name']}")
                continue
            if sha256_file(zip_path) != artifact["sha256"]:
                problems.append(f"artifact hash mismatch: {artifact['name']}")
            try:
                assert_zip_entries_match(
                    zip_path, artifact["entries"], where=artifact["name"]
                )
            except CheckFailed as exc:
                problems.append(str(exc))
                continue
            target = tmpdir / artifact["name"].replace(".zip", "")
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(target)
            for entry in artifact["entries"]:
                extracted = target / entry["name"]
                if not extracted.is_file():
                    problems.append(
                        f"{artifact['name']}: extracted entry missing {entry['name']}"
                    )
                elif sha256_file(extracted) != entry["sha256"]:
                    problems.append(
                        f"{artifact['name']}: extracted entry hash mismatch {entry['name']}"
                    )

    # Skills inside the package tree
    for skill in SKILLS:
        problems.extend(
            verify_skill_tree(PACKAGE / "skills" / skill, where=f"skills/{skill}")
        )
        archive_path = release_dir / f"skill-{skill}.zip"
        if not archive_path.is_file():
            problems.append(f"skill zip missing: skill-{skill}.zip")
            continue
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
        if "SKILL.md" not in names:
            problems.append(f"skill-{skill}.zip: SKILL.md is not at the archive root")
        try:
            verify_plugin_archive(release_dir / f"plugin-{skill}.zip", skill)
        except (CheckFailed, FileNotFoundError) as exc:
            problems.append(str(exc))

    # Tutor pack must not carry answer material
    tutor_zip = release_dir / "tutor-v1.zip"
    if tutor_zip.is_file():
        with zipfile.ZipFile(tutor_zip) as archive:
            for name in archive.namelist():
                if not name.endswith(".json"):
                    continue
                payload = json.loads(archive.read(name))
                for problem in walk_keys(payload, where=f"tutor-v1.zip:{name}"):
                    problems.append(problem)
    classroom_manifest = read_json(PACKAGE / "bundles" / "classroom" / "manifest.json")
    if classroom_manifest.get("contains_answer_material") is not False:
        problems.append("classroom bundle declares answer material")
    for item in classroom_manifest["items"]:
        problems.extend(
            scan_text(
                json.dumps(read_json(ROOT / item["path"]), ensure_ascii=False),
                where=item["path"],
            )
        )
        problems.extend(walk_keys(read_json(ROOT / item["path"]), where=item["path"]))
    bundle_manifest = read_json(PACKAGE / "bundles" / "manifest.json")
    if bundle_manifest["separation"]["answers_in_tutor_bundle"] is not False:
        problems.append("bundle manifest reports answers in the Tutor bundle")
    if bundle_manifest["designer_private"]["included_items"]:
        problems.append("designer private manifest unexpectedly lists shipped items")

    # Quiz sample: answers stay private
    problems.extend(
        verify_quiz_sample(
            PACKAGE / "designer" / "v1" / "examples" / "quiz-draft.sample.json",
            where="designer/v1/examples/quiz-draft.sample.json",
        )
    )

    # Deployment separation
    deploy = read_json(PACKAGE / "deployment-manifest.json")
    if deploy.get("deployment_status") != "NOT_DEPLOYED":
        if not deploy.get("deployment_verified"):
            problems.append(
                "deployment manifest claims deployment without verification"
            )
    for role, target in deploy.get("bot_roles", {}).items():
        if target.get("bot_id") is not None or target.get("workspace_id") is not None:
            problems.append(f"{role}: deployment IDs belong in the server registry")
    if deploy.get("deployment_verified") is not False:
        problems.append("deployment_verified must stay false without platform evidence")
    if deploy["release_id"] != release_id:
        problems.append("deployment manifest release_id mismatch")
    release_deployment = read_json(release_dir / "deployment-manifest.json")
    if release_deployment != deploy:
        problems.append("release deployment manifest differs from canonical manifest")

    # Reproducibility
    if check_reproducible:
        with tempfile.TemporaryDirectory() as tmp:
            rebuilt = Path(tmp)
            for artifact in manifest["artifacts"]:
                spec = next(
                    item
                    for item in artifact_specs()
                    if item["name"] == artifact["name"]
                )
                candidate = rebuilt / spec["name"]
                build_artifact(candidate, spec)
                if sha256_file(candidate) != artifact["sha256"]:
                    problems.append(f"artifact not reproducible: {artifact['name']}")
    return problems


def scan_package_tree(root: Path = PACKAGE) -> list[str]:
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        where = (
            rel(path)
            if path.is_relative_to(ROOT)
            else str(path.relative_to(root)).replace("\\", "/")
        )
        problems.extend(scan_text(text, where=where))
    return problems


# --------------------------------------------------------------------------- #
# Self test (negative cases)
# --------------------------------------------------------------------------- #


def selftest() -> int:
    failures: list[str] = []
    release_id = DEFAULT_RELEASE_ID
    release_dir = PACKAGE / "releases" / release_id
    manifest_path = release_dir / "release-manifest.json"
    if not manifest_path.is_file():
        print("selftest requires a built release; run build first", file=sys.stderr)
        return 2
    manifest = read_json(manifest_path)
    tutor_zip = release_dir / "tutor-v1.zip"
    classroom_zip = release_dir / "bundles-classroom.zip"

    def expect_failure(label: str, fn) -> None:  # noqa: ANN001 - local helper
        try:
            fn()
        except CheckFailed as exc:
            print(f"OK   {label}: detected -> {exc}")
            return
        except Exception as exc:  # noqa: BLE001 - report unexpected error types
            failures.append(f"{label}: unexpected error {exc!r}")
            return
        failures.append(f"{label}: tampering was NOT detected")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        # Plugin replacement uploads require an author object, unlike bare Skill ZIPs.
        plugin_zip = release_dir / "plugin-k12-teaching-core.zip"
        missing_author = tmpdir / "missing-author.zip"
        with (
            zipfile.ZipFile(plugin_zip) as source,
            zipfile.ZipFile(missing_author, "w") as target,
        ):
            for entry in source.infolist():
                data = source.read(entry)
                if entry.filename == ".claude-plugin/plugin.json":
                    metadata = json.loads(data)
                    metadata.pop("author")
                    data = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
                target.writestr(entry, data)
        expect_failure(
            "missing Plugin author",
            lambda: verify_plugin_archive(missing_author, "k12-teaching-core"),
        )
        verify_plugin_archive(plugin_zip, "k12-teaching-core")
        print("OK   Plugin author control: complete manifest stays valid")

        # 1. tampered entry vs manifest
        target = tmpdir / "tutor-v1.zip"
        shutil.copyfile(tutor_zip, target)
        tampered = tmpdir / "tampered"
        with zipfile.ZipFile(target) as archive:
            archive.extractall(tampered)
        prompt = next(tampered.rglob("system-prompt.md"))
        prompt.write_text(
            prompt.read_text(encoding="utf-8") + "\n篡改\n", encoding="utf-8"
        )
        entries = collect_entries(tampered, "")
        rebuilt = tmpdir / "tampered.zip"
        build_zip(rebuilt, entries)
        expected = next(
            a for a in manifest["artifacts"] if a["name"] == "tutor-v1.zip"
        )["entries"]
        expect_failure(
            "tampered entry",
            lambda: assert_zip_entries_match(rebuilt, expected, where="tampered.zip"),
        )

        # 2. traversal entry
        traversal = tmpdir / "traversal.zip"
        with zipfile.ZipFile(traversal, "w") as archive:
            archive.writestr("../evil.txt", "x")
        expect_failure(
            "traversal entry",
            lambda: zip_entry_records(traversal),
        )

        # 3. absolute-path entry
        absolute = tmpdir / "absolute.zip"
        with zipfile.ZipFile(absolute, "w") as archive:
            archive.writestr("/tmp/evil.txt", "x")
        expect_failure(
            "absolute entry",
            lambda: zip_entry_records(absolute),
        )

        # 4. injected secret into a classroom item, routed through the real tree scanner
        classroom_item = next((PACKAGE / "bundles" / "classroom").rglob("*-r*.json"))
        clean_root = tmpdir / "pkg-clean"
        dirty_root = tmpdir / "pkg-dirty"
        for tree in (clean_root, dirty_root):
            copied = tree / "bundles" / classroom_item.name
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(classroom_item, copied)
        polluted = dirty_root / "bundles" / classroom_item.name
        payload = read_json(polluted)
        payload["notes"] = "-----BEGIN RSA PRIVATE KEY-----"
        write_json(polluted, payload)

        def injected_secret_detected() -> None:
            problems = scan_package_tree(dirty_root)
            if problems:
                raise CheckFailed(problems[0])

        expect_failure("injected secret", injected_secret_detected)
        clean_problems = scan_package_tree(clean_root)
        if clean_problems:
            failures.append(
                f"injected secret control: clean tree was flagged ({clean_problems[0]})"
            )
        else:
            print("OK   injected secret control: clean tree stays clean")

        # 5. modified schema copy
        skills_dir = tmpdir / "skills" / "k12-teaching-core" / "references"
        skills_dir.mkdir(parents=True)
        schema = CONTRACTS / "teaching-request.schema.json"
        modified = json.loads(schema.read_text(encoding="utf-8"))
        modified["title"] = modified.get("title", "") + " (tampered)"
        write_json(skills_dir / "teaching-request.schema.json", modified)
        shutil.copyfile(
            PACKAGE / "skills" / "k12-teaching-core" / "SKILL.md",
            tmpdir / "skills" / "k12-teaching-core" / "SKILL.md",
        )
        shutil.copyfile(
            PACKAGE
            / "skills"
            / "k12-teaching-core"
            / "references"
            / "stage-policy.json",
            skills_dir / "stage-policy.json",
        )
        shutil.copyfile(
            PACKAGE
            / "skills"
            / "k12-teaching-core"
            / "references"
            / "teaching-response.schema.json",
            skills_dir / "teaching-response.schema.json",
        )
        problems = verify_skill_tree(
            tmpdir / "skills" / "k12-teaching-core", where="tampered-skill"
        )
        if any("differs from frozen contract" in problem for problem in problems):
            print("OK   modified schema: detected -> schema byte comparison failed")
        else:
            failures.append(f"modified schema: NOT detected ({problems})")

        # 6. classroom zip must stay free of answer keys
        with zipfile.ZipFile(classroom_zip) as archive:
            for name in archive.namelist():
                if not name.endswith(".json"):
                    continue
                payload = json.loads(archive.read(name))
                if walk_keys(payload, where=name):
                    failures.append(f"classroom bundle contains forbidden keys: {name}")

    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    print(f"selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_bundles_cmd = sub.add_parser(
        "build-bundles", help="regenerate the classroom bundle"
    )
    build_bundles_cmd.add_argument("--release-id", default=DEFAULT_RELEASE_ID)

    build_cmd = sub.add_parser("build", help="build the release ZIPs and manifests")
    build_cmd.add_argument("--release-id", default=DEFAULT_RELEASE_ID)

    verify_cmd = sub.add_parser("verify", help="verify a built release")
    verify_cmd.add_argument("--release-id", default=DEFAULT_RELEASE_ID)
    verify_cmd.add_argument("--no-reproducible", action="store_true")

    sub.add_parser("scan", help="scan the package tree for secrets and absolute paths")
    sub.add_parser("selftest", help="run negative-case checks")

    args = parser.parse_args(argv)

    if args.command == "build-bundles":
        manifest = build_bundles(args.release_id)
        print(
            f"bundles: kind={manifest['bundle_kind']} tutor_visible={manifest['separation']['tutor_visible_count']} "
            f"designer_private={manifest['separation']['designer_private_count']}"
        )
        return 0

    if args.command == "build":
        manifest = build_release(args.release_id)
        print(
            f"release {manifest['release_id']} built with {len(manifest['artifacts'])} artifacts"
        )
        for artifact in manifest["artifacts"]:
            print(
                f"  {artifact['name']}: {artifact['sha256']} ({artifact['bytes']} bytes)"
            )
        return 0

    if args.command == "verify":
        problems = verify_release(
            args.release_id, check_reproducible=not args.no_reproducible
        )
        problems.extend(scan_package_tree())
        if problems:
            for problem in problems:
                print(f"FAIL {problem}", file=sys.stderr)
            return 1
        print(
            "PASS verify: ZIP safety, hashes, schemas, answer separation, deployment status"
        )
        return 0

    if args.command == "scan":
        problems = scan_package_tree()
        if problems:
            for problem in problems:
                print(f"FAIL {problem}", file=sys.stderr)
            return 1
        print("PASS scan: no secrets, keys or absolute paths in platform/knodo")
        return 0

    if args.command == "selftest":
        return selftest()

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
