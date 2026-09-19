"""The four fixed agent operations (T03 semantic contract).

Tutor executes TEACH_TURN / CODE_FEEDBACK; Designer executes QUIZ_DRAFT /
LESSON_PACKAGE_DRAFT. Any other value is fail-closed: the gateway rejects it
instead of guessing an operation or falling back to another provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

Role = Literal["tutor", "designer"]


class Operation(StrEnum):
    TEACH_TURN = "TEACH_TURN"
    CODE_FEEDBACK = "CODE_FEEDBACK"
    QUIZ_DRAFT = "QUIZ_DRAFT"
    LESSON_PACKAGE_DRAFT = "LESSON_PACKAGE_DRAFT"


class UnknownOperation(ValueError):
    """Raised when a caller asks for an operation outside the fixed four."""


@dataclass(frozen=True)
class OperationSpec:
    operation: Operation
    role: Role
    request_schema: str
    response_schema: str


OPERATION_SPECS: dict[Operation, OperationSpec] = {
    Operation.TEACH_TURN: OperationSpec(
        Operation.TEACH_TURN, "tutor", "teaching-request", "teaching-response"
    ),
    Operation.CODE_FEEDBACK: OperationSpec(
        Operation.CODE_FEEDBACK, "tutor", "teaching-request", "teaching-response"
    ),
    Operation.QUIZ_DRAFT: OperationSpec(
        Operation.QUIZ_DRAFT, "designer", "designer-request", "quiz-draft"
    ),
    Operation.LESSON_PACKAGE_DRAFT: OperationSpec(
        Operation.LESSON_PACKAGE_DRAFT, "designer", "designer-request", "lesson-package-draft"
    ),
}

TUTOR_OPERATIONS = frozenset(op for op, spec in OPERATION_SPECS.items() if spec.role == "tutor")
DESIGNER_OPERATIONS = frozenset(
    op for op, spec in OPERATION_SPECS.items() if spec.role == "designer"
)


def parse_operation(value: object) -> Operation:
    """Return the fixed Operation or raise UnknownOperation (fail-closed)."""

    if isinstance(value, Operation):
        return value
    if not isinstance(value, str):
        raise UnknownOperation("operation must be one of the four fixed ids")
    try:
        return Operation(value)
    except ValueError as exc:
        raise UnknownOperation(f"unknown operation: {value!r}") from exc
