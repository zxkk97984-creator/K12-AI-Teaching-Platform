from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.core.database import engine_for
from app.modules.codelab.contracts import (
    DEFAULT_CATALOG_METADATA_PATH,
    DEFAULT_CATALOG_ROOT,
    load_catalog,
    load_catalog_metadata,
    task_definition_hash,
)
from app.modules.codelab.models import CodeTaskCatalog, CodeTaskRevision
from app.modules.codelab.trusted import validate_trusted_manifest

logger = logging.getLogger(__name__)


class TaskRevisionConflict(ValueError):
    """A stable task revision was changed instead of being versioned."""


@dataclass
class ImportResult:
    dry_run: bool
    created: int = 0
    reused: int = 0
    tasks: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "created": self.created,
            "reused": self.reused,
            "total": len(self.tasks),
            "tasks": self.tasks,
        }


async def import_catalog(
    session: AsyncSession,
    *,
    catalog_root: Path = DEFAULT_CATALOG_ROOT,
    metadata_path: Path | None = None,
    dry_run: bool = False,
) -> ImportResult:
    loaded = load_catalog(catalog_root)
    if metadata_path is None and catalog_root.resolve() == DEFAULT_CATALOG_ROOT.resolve():
        metadata_path = DEFAULT_CATALOG_METADATA_PATH
    metadata = load_catalog_metadata(metadata_path) if metadata_path is not None else {}
    task_keys = {(task.task_id, task.revision) for _, task in loaded}
    unexpected_metadata = set(metadata) - task_keys
    if unexpected_metadata:
        first = sorted(unexpected_metadata)[0]
        raise ValueError(f"catalogue metadata has no matching task: {first[0]}@r{first[1]}")
    result = ImportResult(dry_run=dry_run)
    try:
        for _path, task in loaded:
            validate_trusted_manifest(
                task.task_id,
                expected_count=task.test_manifest.hidden_case_count,
                expected_sha256=task.test_manifest.hidden_cases_sha256,
            )
            definition_hash = task_definition_hash(task)
            existing = await session.scalar(
                select(CodeTaskRevision).where(
                    CodeTaskRevision.task_id == task.task_id,
                    CodeTaskRevision.revision == task.revision,
                )
            )
            label = f"{task.task_id}@r{task.revision}"
            result.tasks.append(label)
            if existing is not None:
                if existing.definition_sha256 != definition_hash:
                    raise TaskRevisionConflict(
                        f"{label} already exists with a different definition; create a new revision"
                    )
                result.reused += 1
                continue
            session.add(
                CodeTaskRevision(
                    task_id=task.task_id,
                    revision=task.revision,
                    status=task.status,
                    is_test_fixture=task.is_test_fixture,
                    review_status=task.review_status,
                    title=task.title,
                    description=task.description,
                    starter_code=task.starter_code,
                    entrypoint=task.entrypoint,
                    io_contract=task.io_contract.model_dump(mode="json"),
                    examples=[example.model_dump(mode="json") for example in task.examples],
                    test_manifest=task.test_manifest.model_dump(mode="json"),
                    rubric=task.rubric.model_dump(mode="json"),
                    chapter_binding=task.chapter_binding.model_dump(mode="json"),
                    source=task.source.model_dump(mode="json"),
                    definition_sha256=definition_hash,
                )
            )
            result.created += 1
        await session.flush()
        for (task_id, revision), item in metadata.items():
            statement = pg_insert(CodeTaskCatalog).values(
                task_id=task_id,
                task_revision=revision,
                category=item.category,
                difficulty=item.difficulty,
                tags=item.tags,
                sort_order=item.sort_order,
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[CodeTaskCatalog.task_id, CodeTaskCatalog.task_revision],
                    set_={
                        "category": statement.excluded.category,
                        "difficulty": statement.excluded.difficulty,
                        "tags": statement.excluded.tags,
                        "sort_order": statement.excluded.sort_order,
                    },
                )
            )
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


async def _run(catalog_root: Path, metadata_path: Path | None, dry_run: bool) -> ImportResult:
    settings = get_settings()
    engine = engine_for(settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await import_catalog(
                session, catalog_root=catalog_root, metadata_path=metadata_path, dry_run=dry_run
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import immutable CodeLab task revisions")
    parser.add_argument("--catalog-root", type=Path, default=DEFAULT_CATALOG_ROOT)
    parser.add_argument("--metadata-path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = asyncio.run(_run(args.catalog_root, args.metadata_path, args.dry_run))
    print(
        f"import_codelab_tasks: created={result.created} reused={result.reused} "
        f"total={len(result.tasks)} dry_run={result.dry_run}"
    )


if __name__ == "__main__":
    main()
