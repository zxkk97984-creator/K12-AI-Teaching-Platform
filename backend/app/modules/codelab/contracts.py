from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG_ROOT = REPO_ROOT / "curriculum" / "code-tasks"
DEFAULT_CATALOG_METADATA_PATH = REPO_ROOT / "curriculum" / "code-task-catalog.json"
TASK_SCHEMA_VERSION = "k12.code-task.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Limits(StrictModel):
    max_input_bytes: int = Field(ge=1, le=1_048_576)
    max_output_bytes: int = Field(ge=1, le=1_048_576)
    timeout_ms: int = Field(ge=1, le=30_000)


class IOContract(StrictModel):
    protocol: Literal["function-json.v1"]
    language: Literal["python"]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    limits: Limits
    errors: list[
        Literal[
            "INVALID_JSON",
            "INVALID_INPUT",
            "STUDENT_EXCEPTION",
            "TIMEOUT",
            "OUTPUT_LIMIT",
            "SYSTEM_ERROR",
        ]
    ] = Field(min_length=1)


class PublicExample(StrictModel):
    input: dict[str, Any]
    output: Any


class PublicGroup(StrictModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{0,31}$")
    name: str = Field(min_length=1, max_length=120)
    dimension: Literal["F", "R"]
    max_score: float = Field(gt=0)
    case_count: int = Field(ge=1)


class TestManifest(StrictModel):
    oracle_boundary: Literal["TRUSTED_RUNNER_ONLY"]
    public_groups: list[PublicGroup] = Field(min_length=1)
    hidden_case_count: int = Field(ge=1)
    hidden_cases_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_groups(self) -> TestManifest:
        ids = [group.id for group in self.public_groups]
        if len(ids) != len(set(ids)):
            raise ValueError("test manifest group ids must be unique")
        totals = {dimension: 0.0 for dimension in ("F", "R")}
        for group in self.public_groups:
            totals[group.dimension] += group.max_score
        if totals != {"F": 60.0, "R": 10.0}:
            raise ValueError("test manifest must total F=60 and R=10")
        if sum(group.case_count for group in self.public_groups) != self.hidden_case_count:
            raise ValueError("hidden_case_count must match the trusted case count")
        if self.hidden_cases_sha256 == "0" * 64:
            raise ValueError("hidden cases must have a real manifest digest")
        return self


class Rubric(StrictModel):
    version: Literal["k12.codelab.rubric.v1"]
    deterministic_dimensions: list[dict[str, Any]] = Field(min_length=2)
    score_scale: Literal[70]
    ai_feedback_non_authoritative: Literal[True]

    @model_validator(mode="after")
    def validate_deterministic_dimensions(self) -> Rubric:
        dimensions = {
            item.get("id"): item.get("max_score")
            for item in self.deterministic_dimensions
            if isinstance(item, dict)
        }
        if dimensions != {"F": 60, "R": 10}:
            raise ValueError("deterministic rubric must contain exactly F=60 and R=10")
        return self


class ChapterBinding(StrictModel):
    release_key: str = Field(min_length=1)
    course_slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    chapter_slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    revision: int = Field(ge=1)
    stage: Literal["PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"]
    knowledge_point_slugs: list[str] = Field(min_length=1)


class Source(StrictModel):
    source_kind: Literal["LEGACY_REUSED"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str = Field(min_length=1)
    legacy_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_solution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    legacy_test_groups_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SyntheticSource(StrictModel):
    source_kind: Literal["SYNTHETIC_FIXTURE"]
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_solution_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CatalogMetadata(StrictModel):
    task_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    task_revision: int = Field(ge=1)
    category: Literal["PYTHON_BASICS", "DATA_PROCESSING", "ALGORITHMS"]
    difficulty: Literal["EASY", "MEDIUM", "HARD"]
    tags: list[str] = Field(max_length=12)
    sort_order: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_tags(self) -> CatalogMetadata:
        if any(not tag.strip() or len(tag) > 40 for tag in self.tags):
            raise ValueError("catalog tags must contain 1 to 40 characters")
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("catalog tags must be unique")
        return self


class CatalogMetadataDocument(StrictModel):
    schema_version: Literal["k12.code-task-catalog.v1"]
    items: list[CatalogMetadata]


class TaskDefinition(StrictModel):
    schema_version: Literal["k12.code-task.v1"]
    task_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    revision: int = Field(ge=1)
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
    is_test_fixture: bool
    review_status: Literal["UNREVIEWED", "HUMAN_REVIEWED"]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=12_000)
    starter_code: str = Field(min_length=1, max_length=20_000)
    entrypoint: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
    io_contract: IOContract
    examples: list[PublicExample] = Field(min_length=1, max_length=8)
    test_manifest: TestManifest
    rubric: Rubric
    chapter_binding: ChapterBinding
    source: Annotated[Source | SyntheticSource, Field(discriminator="source_kind")]

    @model_validator(mode="after")
    def validate_boundaries(self) -> TaskDefinition:
        if f"def {self.entrypoint}(" not in self.starter_code:
            raise ValueError("starter_code must define the declared entrypoint")
        if self.source.source_kind == "SYNTHETIC_FIXTURE" and not self.is_test_fixture:
            raise ValueError("synthetic source must be marked as a test fixture")
        if self.is_test_fixture and self.source.source_kind != "SYNTHETIC_FIXTURE":
            raise ValueError("test fixtures must have a synthetic source")
        if self.review_status == "HUMAN_REVIEWED" and self.status == "DRAFT":
            raise ValueError("a human-reviewed task cannot remain DRAFT")
        if self.status == "PUBLISHED" and self.review_status != "HUMAN_REVIEWED":
            raise ValueError("a published task requires a human review")
        if self.chapter_binding.revision != self.revision:
            raise ValueError("task and chapter revisions must match")
        return self


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def task_definition_hash(task: TaskDefinition) -> str:
    return hashlib.sha256(canonical_json(task.model_dump(mode="json")).encode()).hexdigest()


def _reject_secret_fields(payload: Any, path: str = "task") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"reference_solution", "hidden_tests", "test_groups", "tests"}:
                raise ValueError(f"{path}.{key} is not allowed in the trusted task manifest")
            _reject_secret_fields(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _reject_secret_fields(value, f"{path}[{index}]")


def parse_task_document(payload: dict[str, Any]) -> TaskDefinition:
    _reject_secret_fields(payload)
    source = payload.get("source")
    if isinstance(source, dict) and source.get("source_kind") == "SYNTHETIC_FIXTURE":
        source_hash = source.get("source_sha256")
        unhashed = {key: value for key, value in payload.items() if key != "source"}
        expected = hashlib.sha256(canonical_json(unhashed).encode("utf-8")).hexdigest()
        if source_hash != expected:
            raise ValueError("synthetic source_sha256 does not match the task document")
    return TaskDefinition.model_validate(payload)


def load_catalog(root: Path = DEFAULT_CATALOG_ROOT) -> list[tuple[Path, TaskDefinition]]:
    if not root.is_dir():
        raise FileNotFoundError(f"code task catalog does not exist: {root}")
    loaded: list[tuple[Path, TaskDefinition]] = []
    seen: set[tuple[str, int]] = set()
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        task = parse_task_document(payload)
        key = (task.task_id, task.revision)
        if key in seen:
            raise ValueError(f"duplicate task revision: {task.task_id}@r{task.revision}")
        seen.add(key)
        loaded.append((path, task))
    if not loaded:
        raise ValueError(f"code task catalog is empty: {root}")
    return loaded


def load_catalog_metadata(
    path: Path = DEFAULT_CATALOG_METADATA_PATH,
) -> dict[tuple[str, int], CatalogMetadata]:
    """Load the separately versioned, student-facing task catalogue metadata."""
    if not path.is_file():
        return {}
    document = CatalogMetadataDocument.model_validate_json(path.read_text(encoding="utf-8"))
    result: dict[tuple[str, int], CatalogMetadata] = {}
    for item in document.items:
        key = (item.task_id, item.task_revision)
        if key in result:
            raise ValueError(f"duplicate catalogue metadata: {item.task_id}@r{item.task_revision}")
        result[key] = item
    return result


def public_task_view(task: TaskDefinition) -> dict[str, Any]:
    """Return the student-safe DTO; trusted manifest fields are intentionally omitted."""

    return {
        "schema_version": task.schema_version,
        "task_id": task.task_id,
        "revision": task.revision,
        "status": task.status,
        "is_test_fixture": task.is_test_fixture,
        "title": task.title,
        "description": task.description,
        "starter_code": task.starter_code,
        "entrypoint": task.entrypoint,
        "io_contract": task.io_contract.model_dump(mode="json"),
        "examples": [example.model_dump(mode="json") for example in task.examples],
        "public_test_groups": [
            group.model_dump(mode="json") for group in task.test_manifest.public_groups
        ],
        "chapter_binding": task.chapter_binding.model_dump(mode="json"),
    }
