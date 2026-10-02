"""Runtime models built from the five frozen T03 semantic schemas.

The gateway must speak the *same* semantics as ``contracts/*.schema.json``.
Instead of hand-copying the schemas into Pydantic models (which drifts), the
models are translated from the frozen JSON Schema files at import time. Any
keyword outside the supported subset raises :class:`UnsupportedSchemaFeature`,
so an unnoticed schema change fails loudly instead of silently under-validating.

Validation error messages carry only field paths and pydantic error *types*:
never the offending input, so raw JSON cannot leak through the API (QA12).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    create_model,
)

from app.integrations.knodo.operations import OPERATION_SPECS, Operation

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = PROJECT_ROOT / "contracts"

CONTRACT_SCHEMA_FILES = {
    "teaching-request": "teaching-request.schema.json",
    "teaching-response": "teaching-response.schema.json",
    "teaching-turn-response": "teaching-turn-response.schema.json",
    "designer-request": "designer-request.schema.json",
    "quiz-draft": "quiz-draft.schema.json",
    "lesson-package-draft": "lesson-package-draft.schema.json",
}

SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "const",
        "enum",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "anyOf",
        "oneOf",
        "allOf",
        "if",
        "then",
        "else",
    }
)
METADATA_KEYWORDS = frozenset({"$schema", "title", "description"})


class UnsupportedSchemaFeature(RuntimeError):
    """The frozen schema uses a JSON Schema keyword this builder cannot honour."""


class MissingContractSchema(RuntimeError):
    """A frozen contract file is absent: the gateway must stay unavailable."""


def _check_keywords(node: Any, *, where: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("properties",):
                for field_name, subschema in value.items():
                    _check_keywords(subschema, where=f"{where}.{field_name}")
                continue
            if key in METADATA_KEYWORDS:
                continue
            if key not in SUPPORTED_KEYWORDS:
                raise UnsupportedSchemaFeature(f"{where}: unsupported keyword {key!r}")
            _check_keywords(value, where=f"{where}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _check_keywords(item, where=f"{where}[{index}]")


def _union(variants: tuple[Any, ...]) -> Any:
    """Build ``A | B | ...`` at runtime (schema variants are data, not syntax)."""

    result = variants[0]
    for variant in variants[1:]:
        result = result | variant
    return result


def _unique_items(items: list[Any]) -> list[Any]:
    seen: list[Any] = []
    for item in items:
        if item in seen:
            raise ValueError("array items must be unique")
        seen.append(item)
    return items


def _build(node: dict[str, Any], name: str, *, where: str) -> Any:
    node_type = node.get("type")

    if isinstance(node_type, list):
        variants = tuple(
            _build({**node, "type": single}, f"{name}_{single}", where=where)
            for single in node_type
        )
        return _union(variants)

    if "const" in node:
        return Literal[node["const"]]  # type: ignore[valid-type]
    if "enum" in node:
        return Literal[tuple(node["enum"])]  # type: ignore[valid-type]

    union_key = "anyOf" if "anyOf" in node else ("oneOf" if "oneOf" in node else None)
    if union_key is not None:
        variants = tuple(
            _build(subschema, f"{name}_v{index}", where=f"{where}.{union_key}[{index}]")
            for index, subschema in enumerate(node[union_key])
        )
        return _union(variants)

    if "allOf" in node:
        base_schema = {key: value for key, value in node.items() if key != "allOf"}
        base = _build(base_schema, name, where=where)
        checks = tuple(
            _build_conditional(cond, where=f"{where}.allOf[{index}]")
            for index, cond in enumerate(node["allOf"])
        )

        def combined(value: Any) -> Any:
            for check in checks:
                value = check(value)
            return value

        return Annotated[base, AfterValidator(combined)]

    if node_type == "object":
        fields: dict[str, Any] = {}
        required = set(node.get("required", []))
        for field_name, subschema in node.get("properties", {}).items():
            annotation = _build(subschema, f"{name}_{field_name}", where=f"{where}.{field_name}")
            fields[field_name] = (annotation, ...) if field_name in required else (annotation, None)
        extra = "forbid" if node.get("additionalProperties") is False else "allow"
        return create_model(name, __config__=ConfigDict(extra=extra, strict=True), **fields)

    if node_type == "array":
        item_type = _build(node["items"], f"{name}_item", where=f"{where}.items")
        constraints: dict[str, Any] = {}
        if "minItems" in node:
            constraints["min_length"] = node["minItems"]
        if "maxItems" in node:
            constraints["max_length"] = node["maxItems"]
        annotated = Annotated[list[item_type], Field(**constraints)]  # type: ignore[valid-type]
        if node.get("uniqueItems"):
            return Annotated[annotated, AfterValidator(_unique_items)]
        return annotated

    if node_type == "string":
        return Annotated[
            str,
            StringConstraints(
                min_length=node.get("minLength"),
                max_length=node.get("maxLength"),
            ),
        ]

    if node_type == "integer":
        constraints = {}
        if "minimum" in node:
            constraints["ge"] = node["minimum"]
        if "maximum" in node:
            constraints["le"] = node["maximum"]
        return Annotated[StrictInt, Field(**constraints)]

    if node_type == "number":
        constraints = {}
        if "minimum" in node:
            constraints["ge"] = node["minimum"]
        if "maximum" in node:
            constraints["le"] = node["maximum"]
        return (
            Annotated[StrictInt, Field(**constraints)]
            | Annotated[StrictFloat, Field(**constraints)]
        )

    if node_type == "boolean":
        return StrictBool

    if node_type == "null":
        return type(None)

    raise UnsupportedSchemaFeature(f"{where}: unsupported schema node {sorted(node)!r}")


def _value_matches(schema: dict[str, Any], value: Any) -> bool:
    if "const" in schema:
        return value == schema["const"]
    if "enum" in schema:
        return value in schema["enum"]
    node_type = schema.get("type")
    if isinstance(node_type, list):
        return any(_value_matches({**schema, "type": single}, value) for single in node_type)
    if node_type == "null":
        return value is None
    if node_type == "object":
        return isinstance(value, dict)
    if node_type == "array":
        return isinstance(value, list)
    if node_type == "string":
        return isinstance(value, str)
    if node_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if node_type == "boolean":
        return isinstance(value, bool)
    raise UnsupportedSchemaFeature(f"unsupported conditional schema {sorted(schema)!r}")


def _condition_matches(schema: dict[str, Any], value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for name in schema.get("required", []):
        if name not in value:
            return False
    for name, subschema in schema.get("properties", {}).items():
        if name in value and not _value_matches(subschema, value[name]):
            return False
    return True


def _build_conditional(cond: dict[str, Any], *, where: str):
    allowed = {"if", "then", "else"}
    if not set(cond) <= allowed or "if" not in cond:
        raise UnsupportedSchemaFeature(f"{where}: unsupported allOf branch {sorted(cond)!r}")
    for part_name in ("if", "then", "else"):
        part = cond.get(part_name)
        if part is None:
            continue
        if not set(part) <= {"properties", "required"}:
            raise UnsupportedSchemaFeature(
                f"{where}.{part_name}: unsupported keys {sorted(part)!r}"
            )
        for field_name, subschema in part.get("properties", {}).items():
            if not set(subschema) <= {"type", "const", "enum"}:
                raise UnsupportedSchemaFeature(
                    f"{where}.{part_name}.{field_name}: unsupported keys {sorted(subschema)!r}"
                )

    if_schema = cond["if"]
    branch_then = cond.get("then")
    branch_else = cond.get("else")

    def check(value: Any) -> Any:
        # AfterValidator receives the parsed model: inspect its fields as a dict.
        data = value.model_dump() if isinstance(value, BaseModel) else value
        if not isinstance(data, dict):
            raise ValueError("conditional branch requires an object")
        branch = branch_then if _condition_matches(if_schema, data) else branch_else
        if branch is None:
            return value
        for name in branch.get("required", []):
            if name not in data:
                raise ValueError(f"{name} is required for this operation branch")
        for name, subschema in branch.get("properties", {}).items():
            if name in data and not _value_matches(subschema, data[name]):
                raise ValueError(f"{name} does not match the declared operation branch")
        return value

    return check


def _error_summary(exc: ValidationError) -> list[str]:
    """Field paths + error types only: never echo the submitted payload."""

    summary = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
        summary.append(f"{location}: {error.get('type', 'invalid')}")
    return summary


def _unwrap_model(built: Any) -> type[BaseModel]:
    """Return the underlying model class when the built type is Annotated."""

    candidate = built
    while get_origin(candidate) is not None and not isinstance(candidate, type):
        args = [arg for arg in get_args(candidate) if isinstance(arg, type)]
        if not args:
            break
        candidate = args[0]
    return candidate


class SchemaRegistry:
    """The five frozen schemas plus the request/response models per operation."""

    def __init__(self, schema_dir: Path):
        self.schema_dir = Path(schema_dir)
        self._raw: dict[str, dict[str, Any]] = {}
        self._models: dict[str, type[BaseModel]] = {}
        self._adapters: dict[str, TypeAdapter[Any]] = {}
        self.contract_version = None
        version_file = self.schema_dir / "version.json"
        if not version_file.is_file():
            raise MissingContractSchema(f"contract version file missing: {version_file.name}")
        version_payload = json.loads(version_file.read_text(encoding="utf-8"))
        self.contract_version = version_payload.get("contract_version")
        self.wire_status = version_payload.get("wire_status")
        if not self.contract_version:
            raise MissingContractSchema("contract version file has no contract_version")
        for schema_name, filename in CONTRACT_SCHEMA_FILES.items():
            path = self.schema_dir / filename
            if not path.is_file():
                raise MissingContractSchema(f"contract schema missing: {filename}")
            schema = json.loads(path.read_text(encoding="utf-8"))
            _check_keywords(schema, where=schema_name)
            self._raw[schema_name] = schema
            built = _build(schema, schema_name.replace("-", "_"), where=schema_name)
            self._adapters[schema_name] = TypeAdapter(built)
            self._models[schema_name] = _unwrap_model(built)

    def request_model(self, operation: Operation) -> type[BaseModel]:
        return self._models[OPERATION_SPECS[operation].request_schema]

    def response_model(self, operation: Operation) -> type[BaseModel]:
        return self._models[OPERATION_SPECS[operation].response_schema]

    def raw(self, schema_name: str) -> dict[str, Any]:
        return self._raw[schema_name]

    def validate_request(self, operation: Operation, payload: Any) -> list[str]:
        return self._validate(OPERATION_SPECS[operation].request_schema, payload)

    def validate_response(self, operation: Operation, payload: Any) -> list[str]:
        return self._validate(OPERATION_SPECS[operation].response_schema, payload)

    def validate_schema(self, schema_name: str, payload: Any) -> list[str]:
        """Validate a payload against one frozen schema by name (differential tests)."""

        if schema_name not in self._adapters:
            raise KeyError(f"unknown frozen schema: {schema_name}")
        return self._validate(schema_name, payload)

    def _validate(self, schema_name: str, payload: Any) -> list[str]:
        try:
            self._adapters[schema_name].validate_python(payload)
        except ValidationError as exc:
            return _error_summary(exc)
        return []


@lru_cache(maxsize=4)
def _registry_for(schema_dir: str) -> SchemaRegistry:
    return SchemaRegistry(Path(schema_dir))


def default_registry() -> SchemaRegistry:
    return _registry_for(str(CONTRACTS_DIR))
