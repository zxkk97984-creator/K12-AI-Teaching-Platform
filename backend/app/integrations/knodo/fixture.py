"""Deterministic synthetic fixture backend (dev/test only).

Every payload is derived from the frozen synthetic examples in
``contracts/examples`` and is rewritten to echo the caller's request ids, so a
fixture response can never be mistaken for a recorded real sample. The fixture
exists to exercise the gateway's failure taxonomy offline: success, insufficient
evidence, malformed upstream JSON, delay/timeout, cancellation, 401/403/429/5xx
and output-size overflow.
"""

from __future__ import annotations

import asyncio
import copy
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.integrations.knodo.errors import GatewayError, GatewayErrorCategory
from app.integrations.knodo.operations import Operation
from app.integrations.knodo.schema_models import default_registry
from app.integrations.knodo.types import BackendOutcome

FIXTURE_NOTICE = "SYNTHETIC_FIXTURE_FOR_DEV_TEST_ONLY_NOT_A_REAL_SAMPLE"
CONTRACTS_EXAMPLES = default_registry().schema_dir / "examples"

_TEACHING_RESPONSE_EXAMPLE = "teaching-response"
_QUIZ_DRAFT_EXAMPLE = "quiz-draft"
_LESSON_PACKAGE_EXAMPLE = "lesson-package-draft"


class FixtureScenario(StrEnum):
    SUCCESS = "SUCCESS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MALFORMED_JSON = "MALFORMED_JSON"
    DELAY = "DELAY"
    CANCEL = "CANCEL"
    AUTH_401 = "AUTH_401"
    AUTH_403 = "AUTH_403"
    RATE_429 = "RATE_429"
    SERVER_500 = "SERVER_500"
    OUTPUT_OVER_LIMIT = "OUTPUT_OVER_LIMIT"


def _load_example(name: str) -> dict[str, Any]:
    path = CONTRACTS_EXAMPLES / f"{name}.json"
    return json.loads(Path(path).read_text(encoding="utf-8"))


def teaching_response_payload(operation: Operation, request: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(_load_example(_TEACHING_RESPONSE_EXAMPLE))
    payload["request_id"] = request["request_id"]
    payload["lesson_session_id"] = request["lesson_session_id"]
    payload["base_revision"] = request["base_revision"]
    payload["curriculum_revision"] = request["curriculum_revision"]
    # teaching-response.warnings is a closed enum: use the honest review code.
    payload["warnings"] = ["NEEDS_HUMAN_REVIEW"]
    if operation is Operation.CODE_FEEDBACK:
        facts = request.get("code_feedback_facts") or {}
        payload["message_markdown"] = (
            "这是合成代码反馈样例（非真实学生、非真实运行记录）："
            f"你的代码任务 {facts.get('task_id', 'unknown')} 的执行状态是 "
            f"{facts.get('execution_status', 'NOT_VERIFIED')}，"
            "请先检查思路再修改代码。"
        )
        payload["source_refs"] = []
        payload["evidence_refs"] = []
        payload["action"] = None
    return payload


def designer_payload(operation: Operation, request: dict[str, Any]) -> dict[str, Any]:
    example = _QUIZ_DRAFT_EXAMPLE if operation is Operation.QUIZ_DRAFT else _LESSON_PACKAGE_EXAMPLE
    payload = copy.deepcopy(_load_example(example))
    payload["request_id"] = request["request_id"]
    payload["chapter_id"] = request["chapter_id"]
    payload["curriculum_revision"] = request["curriculum_revision"]
    payload["stage"] = request["stage"]
    warnings = list(payload.get("warnings", []))
    payload["warnings"] = warnings + [FIXTURE_NOTICE]
    return payload


class FixtureGateway:
    """Offline backend. ``invoke`` returns an outcome, never a naked exception."""

    mode = "fixture"

    def __init__(self, *, max_output_bytes: int, default_timeout_seconds: float):
        self.max_output_bytes = max_output_bytes
        self.default_timeout_seconds = default_timeout_seconds

    async def invoke(  # noqa: PLR0911 - explicit scenario dispatch is the point
        self,
        operation: Operation,
        request: dict[str, Any],
        *,
        scenario: FixtureScenario = FixtureScenario.SUCCESS,
        timeout_seconds: float | None = None,
        cancel: asyncio.Event | None = None,
        delay_seconds: float | None = None,
        remote_conversation_id: str | None = None,
    ) -> BackendOutcome:
        del remote_conversation_id
        timeout = timeout_seconds or self.default_timeout_seconds

        if scenario is FixtureScenario.SUCCESS:
            return BackendOutcome(payload=self._success_payload(operation, request))
        if scenario is FixtureScenario.INSUFFICIENT_EVIDENCE:
            payload = self._success_payload(operation, request)
            if operation in (Operation.TEACH_TURN, Operation.CODE_FEEDBACK):
                payload["warnings"] = ["INSUFFICIENT_SOURCE", "NEEDS_HUMAN_REVIEW"]
            else:
                payload["warnings"] = [
                    *payload.get("warnings", []),
                    "INSUFFICIENT_EVIDENCE_FIXTURE",
                ]
            if "source_refs" in payload:
                payload["source_refs"] = []
            return BackendOutcome(payload=payload, insufficient_evidence=True)
        if scenario is FixtureScenario.MALFORMED_JSON:
            return BackendOutcome(
                error=GatewayError(
                    GatewayErrorCategory.VALIDATION, "UPSTREAM_MALFORMED_JSON_FIXTURE"
                )
            )
        if scenario is FixtureScenario.OUTPUT_OVER_LIMIT:
            return BackendOutcome(
                payload={"fixture_oversize": "x" * (self.max_output_bytes + 1024)}
            )
        if scenario in (
            FixtureScenario.AUTH_401,
            FixtureScenario.AUTH_403,
            FixtureScenario.RATE_429,
            FixtureScenario.SERVER_500,
        ):
            status = {
                FixtureScenario.AUTH_401: 401,
                FixtureScenario.AUTH_403: 403,
                FixtureScenario.RATE_429: 429,
                FixtureScenario.SERVER_500: 500,
            }[scenario]
            category = {
                401: GatewayErrorCategory.AUTH,
                403: GatewayErrorCategory.AUTH,
                429: GatewayErrorCategory.RATE,
                500: GatewayErrorCategory.SERVER,
            }[status]
            return BackendOutcome(
                error=GatewayError(category, f"UPSTREAM_{status}", upstream_status=status)
            )

        waited = await self._wait(timeout, cancel, delay_seconds)
        if waited is None:
            return BackendOutcome(cancelled=True)
        if waited is False:
            return BackendOutcome(
                error=GatewayError(GatewayErrorCategory.TIMEOUT, "FIXTURE_TIMEOUT")
            )
        if scenario is FixtureScenario.CANCEL:
            # The caller never signalled cancel: the upstream reports its own cancel.
            return BackendOutcome(
                error=GatewayError(GatewayErrorCategory.CANCEL, "FIXTURE_UPSTREAM_CANCEL")
            )
        return BackendOutcome(payload=self._success_payload(operation, request))

    async def _wait(
        self, timeout: float, cancel: asyncio.Event | None, delay_seconds: float | None
    ) -> bool | None:
        """Wait for ``delay``; True=finished, False=timeout, None=cancelled."""

        delay = delay_seconds if delay_seconds is not None else 1.0
        cancel_wait = asyncio.create_task(cancel.wait()) if cancel is not None else None  # type: ignore[union-attr]
        sleep_task = asyncio.create_task(asyncio.sleep(delay))
        waiters: list[asyncio.Task] = [sleep_task]
        if cancel_wait is not None:
            waiters.append(cancel_wait)
        try:
            done, _ = await asyncio.wait(
                waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in waiters:
                if not task.done():
                    task.cancel()
        if not done:
            return False
        if cancel_wait is not None and cancel_wait in done and cancel_wait.result():
            return None
        return sleep_task in done

    def _success_payload(self, operation: Operation, request: dict[str, Any]) -> dict[str, Any]:
        if operation in (Operation.TEACH_TURN, Operation.CODE_FEEDBACK):
            return teaching_response_payload(operation, request)
        return designer_payload(operation, request)
