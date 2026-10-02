"""Validate complete model output before storing a final teaching card (QA12/QA13).

Rules, in order:

1. the payload must still satisfy the frozen T03 response schema;
2. the text must be safe (length, control characters, no answer/test markers);
3. sources, evidence, actions and resource ids must be inside the session's
   allowed sets — a model cannot mint a source or a clickable resource;
4. the raw payload is never persisted: only the extracted card is stored.

``safe_partial_markdown`` separately gates a provisional stream snapshot. That
snapshot is cleared on terminal status and never enters conversation history.
"""

from __future__ import annotations

from typing import Any

from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry

FORBIDDEN_MARKERS = (
    "correct_answer",
    "hidden_test",
    "hidden_tests",
    "reference_solution",
    "-----BEGIN",
)
CONTROL_CHARS = (
    {chr(code) for code in range(0, 9)} | {chr(11), chr(12)} | {chr(code) for code in range(14, 32)}
)


def safe_partial_markdown(text: str, *, max_chars: int) -> str | None:
    """Return a cautious visible prefix, or None if the draft is unsafe.

    Hold back enough trailing characters to catch a forbidden marker split
    across multiple upstream chunks before any part of that marker is shown.
    The complete response still needs full schema and teaching validation.
    """

    if len(text) > max_chars or any(char in CONTROL_CHARS for char in text):
        return None
    if any(marker.lower() in text.lower() for marker in FORBIDDEN_MARKERS):
        return None
    holdback = max(map(len, FORBIDDEN_MARKERS)) - 1
    return text[: max(0, len(text) - holdback)]


def _allowed(context: dict[str, Any], allowance: dict[str, Any] | None, key: str) -> set[str]:
    values = set(context.get(key, []))
    if allowance:
        values |= set(allowance.get(key, []))
    return values


def validate_assistant_output(
    *,
    operation: Operation,
    payload: dict[str, Any],
    context: dict[str, Any],
    fixture_allowance: dict[str, Any] | None,
) -> list[str]:
    problems: list[str] = []

    # This function validates the final teaching content, never a query plan.
    if default_registry().validate_response(Operation.CODE_FEEDBACK, payload):
        return ["RESPONSE_SCHEMA_MISMATCH"]

    message = str(payload.get("message_markdown", ""))
    max_chars = int(context.get("limits", {}).get("max_reply_chars", 1200))
    if len(message) > max_chars:
        problems.append("MESSAGE_TOO_LONG")
    if any(char in CONTROL_CHARS for char in message):
        problems.append("MESSAGE_UNSAFE_CHARACTERS")
    lowered = message.lower()
    if any(marker.lower() in lowered for marker in FORBIDDEN_MARKERS):
        problems.append("MESSAGE_LEAKS_INTERNALS")

    source_ids = _allowed(context, fixture_allowance, "allowed_source_ids")
    for ref in payload.get("source_refs", []):
        if ref.get("source_id") not in source_ids:
            problems.append("SOURCE_NOT_ALLOWED")
            break

    evidence_ids = _allowed(context, fixture_allowance, "allowed_evidence_ids")
    for ref in payload.get("evidence_refs", []):
        if ref not in evidence_ids:
            problems.append("EVIDENCE_NOT_ALLOWED")
            break

    action = payload.get("action")
    if action is not None:
        actions = _allowed(context, fixture_allowance, "allowed_actions")
        if action.get("type") not in actions:
            problems.append("ACTION_NOT_ALLOWED")
        else:
            bucket = {
                "OPEN_RESOURCE": "allowed_resource_ids",
                "OPEN_ANIMATION": "allowed_animation_ids",
                "OPEN_CODE_TASK": "allowed_code_task_ids",
            }.get(str(action.get("type")))
            if bucket is not None:
                resource_id = (
                    action.get("resource_id") or action.get("animation_id") or action.get("task_id")
                )
                if resource_id not in _allowed(context, fixture_allowance, bucket):
                    problems.append("RESOURCE_NOT_ALLOWED")

    return problems


def build_card(payload: dict[str, Any], *, fixture: bool) -> dict[str, Any]:
    """Student-visible card: extracted fields only, never the raw payload."""

    return {
        "message_markdown": payload["message_markdown"],
        "source_refs": list(payload.get("source_refs", [])),
        "evidence_refs": list(payload.get("evidence_refs", [])),
        "followup_question": payload.get("followup_question"),
        "action": payload.get("action"),
        "phase_suggestion": payload.get("phase_suggestion"),
        "warnings": list(payload.get("warnings", [])),
        "fixture": fixture,
    }
