#!/usr/bin/env python3
"""Convert legacy chapters and import a source package into the content library.

Examples
--------
Convert (writes only ``curriculum/source`` files, never the database)::

    python -m app.scripts.import_content convert \
        --course-file curriculum/source/legacy/k12-library-696364f/courses/\
python-first-steps/course.json \
        --legacy-root /home/zxk/Projects/K12-Learning-platform

Validate a package without writing anything::

    python -m app.scripts.import_content import \
        --release-dir curriculum/source/legacy/k12-library-696364f

Apply it (idempotent) and refresh the release mirror::

    python -m app.scripts.import_content import \
        --release-dir curriculum/source/legacy/k12-library-696364f --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.modules.content.importer import ContentImportError, import_package
from app.modules.content.legacy import convert_course
from app.modules.content.package import PackageValidationError, load_package

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MIRROR_DIR = REPO_ROOT / "curriculum" / "releases"


def _redacted_target(settings: Settings) -> str:
    url = make_url(settings.active_database_url)
    return f"env={settings.app_env} db={url.host}:{url.port}/{url.database}"


def _convert(args: argparse.Namespace) -> int:
    course_files = args.course_file or sorted(
        Path(args.release_dir).resolve().glob("courses/*/course.json")
    )
    if not course_files:
        print("no course files found", file=sys.stderr)
        return 2
    for course_file in course_files:
        results = convert_course(
            Path(course_file), legacy_root=Path(args.legacy_root), check_only=args.check
        )
        for item in results:
            state = (
                "unchanged" if not item.changed else ("written" if not args.check else "CHANGED")
            )
            print(
                f"{item.course_slug}/{item.chapter_slug} r{item.revision}: {state} "
                f"marks={','.join(item.observed_marks) or '-'}"
            )
    return 0


async def _import(args: argparse.Namespace) -> int:
    settings = Settings()
    package = load_package(
        Path(args.release_dir), legacy_root=Path(args.legacy_root) if args.legacy_root else None
    )
    mirror_root = Path(args.mirror_dir).resolve() if args.apply and args.mirror_dir else None
    engine = get_engine(settings.active_database_url, settings.app_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            result = await import_package(
                db,
                package,
                dry_run=not args.apply,
                mirror_root=mirror_root,
            )
    finally:
        await engine.dispose()
    print(f"target: {_redacted_target(settings)}")
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if result.mirror_pending:
        print("mirror incomplete; database is authoritative, re-run to finish", file=sys.stderr)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="convert legacy chapters into source files")
    convert.add_argument("--course-file", action="append", default=None)
    convert.add_argument("--release-dir", default=None)
    convert.add_argument("--legacy-root", required=True)
    convert.add_argument("--check", action="store_true", help="verify without writing")
    convert.set_defaults(handler=_convert)

    importer = sub.add_parser("import", help="validate (and optionally apply) a source package")
    importer.add_argument("--release-dir", required=True)
    importer.add_argument("--apply", action="store_true", help="write rows; default is dry-run")
    importer.add_argument("--mirror-dir", default=str(DEFAULT_MIRROR_DIR))
    importer.add_argument(
        "--legacy-root",
        default=None,
        help="read-only legacy tree used to re-verify original source hashes",
    )
    importer.set_defaults(handler=None)

    args = parser.parse_args(argv)
    if args.command == "convert":
        if not args.course_file and not args.release_dir:
            parser.error("convert needs --course-file or --release-dir")
        try:
            return _convert(args)
        except PackageValidationError as exc:
            print(f"CONVERSION FAILED: {exc}", file=sys.stderr)
            return 2
    try:
        return asyncio.run(_import(args))
    except (PackageValidationError, ContentImportError) as exc:
        print(f"IMPORT FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
