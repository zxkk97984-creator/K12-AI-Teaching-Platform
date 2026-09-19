from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.content.legacy import convert_course, parse_legacy_chapter
from app.modules.content.package import PackageValidationError, load_package
from app.modules.content.schemas import BlockType, Stage
from tests.content_helpers import (
    FIXTURE_PACKAGE,
    LEGACY_PACKAGE,
    build_tiny_legacy_tree,
    chapter_file,
    copy_fixture_package,
    course_file,
    edit_json,
    rewrite_chapter,
)


def test_shipped_legacy_package_loads_with_source_metadata() -> None:
    package = load_package(LEGACY_PACKAGE)
    assert package.release.source_kind.value == "LEGACY_REUSED"
    assert package.release.is_test_fixture is False
    assert package.release.license_code.value == "CC-BY"
    keys = {(item.course.stable_slug, item.spec.stable_slug) for item in package.chapters}
    assert keys == {("algorithm-everyday", "ch03"), ("python-first-steps", "ch05")}
    for item in package.chapters:
        assert len(item.content_hash) == 64
        assert item.spec.source.source_commit.startswith("696364f")
        assert item.blocks[0].type is BlockType.TITLE
        assert item.spec.license_code.value == "CC-BY"


def test_shipped_fixture_package_is_explicitly_synthetic() -> None:
    package = load_package(FIXTURE_PACKAGE)
    assert package.release.is_test_fixture is True
    assert package.release.source_kind.value == "SYNTHETIC_FIXTURE"
    by_slug = {item.spec.stable_slug: item for item in package.chapters}
    assert by_slug["ch01"].spec.stage is Stage.PRIMARY_LOWER
    assert (by_slug["ch01"].spec.grade_min, by_slug["ch01"].spec.grade_max) == (1, 3)
    assert by_slug["ch02"].spec.stage is Stage.JUNIOR
    assert (by_slug["ch02"].spec.grade_min, by_slug["ch02"].spec.grade_max) == (None, None)


def test_conversion_is_deterministic_and_rejects_unknown_marker(tmp_path: Path) -> None:
    legacy_root, _package, course_path = build_tiny_legacy_tree(tmp_path)
    results = convert_course(course_path, legacy_root=legacy_root)
    assert results[0].changed is True and results[0].written is True
    # Running again is a no-op; --check style validation must pass unchanged.
    again = convert_course(course_path, legacy_root=legacy_root, check_only=True)
    assert again[0].changed is False

    source = legacy_root / "books/tiny-book/ch01.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "X: 这是一个未知标记\n", encoding="utf-8"
    )
    with pytest.raises(PackageValidationError):
        convert_course(course_path, legacy_root=legacy_root, check_only=True)


def test_converter_rejects_undeclared_knowledge_point_mark(tmp_path: Path) -> None:
    legacy_root, _package, course_path = build_tiny_legacy_tree(tmp_path)
    source = legacy_root / "books/tiny-book/ch01.md"
    source.write_text(
        source.read_text(encoding="utf-8").replace("CALL:", "@kp=not-declared\nCALL:"),
        encoding="utf-8",
    )
    # Source hash no longer matches the declared value, which is itself a hard error.
    with pytest.raises(PackageValidationError):
        convert_course(course_path, legacy_root=legacy_root)


def test_converter_reports_unknown_meta_key(tmp_path: Path) -> None:
    legacy_root, _package, _course = build_tiny_legacy_tree(tmp_path)
    text = (legacy_root / "books/tiny-book/ch01.md").read_text(encoding="utf-8")
    with pytest.raises(PackageValidationError):
        parse_legacy_chapter(text.replace("summary:", "summary_extra:"), where="inline")


def test_missing_source_file_is_rejected(tmp_path: Path) -> None:
    legacy_root, _package, course_path = build_tiny_legacy_tree(tmp_path)
    (legacy_root / "books/tiny-book/ch01.md").unlink()
    with pytest.raises(PackageValidationError):
        convert_course(course_path, legacy_root=legacy_root)


def test_source_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    legacy_root, _package, course_path = build_tiny_legacy_tree(tmp_path)
    source = legacy_root / "books/tiny-book/ch01.md"
    source.write_text(source.read_text(encoding="utf-8") + "\nP: 追加的正文。\n", encoding="utf-8")
    with pytest.raises(PackageValidationError):
        convert_course(course_path, legacy_root=legacy_root)


def test_traversal_and_absolute_paths_are_rejected(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)
    edit_json(
        course_file(package),
        lambda data: data["chapters"][0].__setitem__("content_file", "../../etc/passwd"),
    )
    with pytest.raises(PackageValidationError):
        load_package(package)

    package = copy_fixture_package(tmp_path / "second")
    edit_json(
        course_file(package),
        lambda data: data["chapters"][0]["source"].__setitem__(
            "source_path", "/home/zxk/Projects/K12-Learning-platform/etc/passwd"
        ),
    )
    with pytest.raises(PackageValidationError):
        load_package(package)


def test_grade_range_must_match_stage(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)
    edit_json(course_file(package), lambda data: data["chapters"][0].__setitem__("grade_min", 6))
    with pytest.raises(PackageValidationError):
        load_package(package)

    package = copy_fixture_package(tmp_path / "second")
    edit_json(course_file(package), lambda data: data["chapters"][0].__setitem__("grade_min", None))
    with pytest.raises(PackageValidationError):
        load_package(package)


def test_unknown_license_is_rejected(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)
    edit_json(
        course_file(package),
        lambda data: data["chapters"][0].__setitem__("license_code", "PROPRIETARY-XYZ"),
    )
    with pytest.raises(PackageValidationError):
        load_package(package)


def test_duplicate_chapter_slug_is_rejected(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)

    def duplicate(data: dict) -> None:
        data["chapters"][1]["stable_slug"] = data["chapters"][0]["stable_slug"]

    edit_json(course_file(package), duplicate)
    with pytest.raises(PackageValidationError):
        load_package(package)


def test_duplicate_knowledge_point_relation_is_rejected(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)
    edit_json(
        course_file(package),
        lambda data: data["chapters"][0].__setitem__(
            "knowledge_points", ["fixture-notice", "fixture-notice"]
        ),
    )
    with pytest.raises(PackageValidationError):
        load_package(package)


def test_missing_figure_asset_is_rejected(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)
    document = json.loads(chapter_file(package, "ch01").read_text(encoding="utf-8"))
    blocks = document["blocks"]
    blocks.append(
        {
            "type": "FIGURE",
            "alt": "缺失资源的图",
            "caption": "资源不存在",
            "src": "assets/missing.svg",
        }
    )
    rewrite_chapter(package, "ch01", blocks)
    with pytest.raises(PackageValidationError):
        load_package(package)


def test_figure_asset_traversal_is_rejected_by_schema(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)
    document = json.loads(chapter_file(package, "ch01").read_text(encoding="utf-8"))
    blocks = list(document["blocks"])
    blocks.append(
        {
            "type": "FIGURE",
            "alt": "越界资源",
            "caption": "不允许的路径",
            "src": "assets/../secret.svg",
        }
    )
    rewrite_chapter(package, "ch01", blocks)
    with pytest.raises(PackageValidationError):
        load_package(package)


def test_orphan_knowledge_point_reference_is_rejected(tmp_path: Path) -> None:
    package = copy_fixture_package(tmp_path)
    edit_json(
        course_file(package),
        lambda data: data["chapters"][0].__setitem__("knowledge_points", ["not-in-catalog"]),
    )
    with pytest.raises(PackageValidationError):
        load_package(package)
