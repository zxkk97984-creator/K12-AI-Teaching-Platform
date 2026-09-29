"""Evidence-backed Knodo Bot Chat mapper.

Official source: the Bot Chat section of ``https://knodo.vip/llms-full.txt``.
Only fields documented there are emitted. The mapper uses the Bot's configured
model, disables tool-result emission, and requests the least
privileged documented permission mode. It never reads a remote conversation ID
from the local semantic payload; continuation IDs must be supplied separately
by trusted backend state.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from app.integrations.knodo.errors import GatewayError, GatewayErrorCategory
from app.integrations.knodo.operations import OPERATION_SPECS, Operation, Role
from app.integrations.knodo.partial import partial_top_level_string
from app.integrations.knodo.transport import Transport, UpstreamRequest
from app.integrations.knodo.types import BackendOutcome

_TARGET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


@dataclass(frozen=True)
class KnodoTarget:
    """Server-owned target identifiers; never populated from learner input."""

    bot_id: str
    workspace_id: str

    def __post_init__(self) -> None:
        if not _TARGET_ID.fullmatch(self.bot_id):
            raise ValueError("invalid Knodo bot id")
        if not _TARGET_ID.fullmatch(self.workspace_id):
            raise ValueError("invalid Knodo workspace id")


class RequestBudget(Protocol):
    async def reserve(self) -> bool:
        """Reserve one request before network submission; unknown outcomes count."""


class InMemoryRequestBudget:
    """Concurrency-safe request cap used by tests and injectable runtimes.

    Production assembly uses the optional durable file-backed budget or the
    unlimited policy in ``budget.py``; this implementation remains useful for
    dependency-injected unit tests.
    """

    def __init__(self, max_requests: int):
        if max_requests < 1:
            raise ValueError("max_requests must be positive")
        self.max_requests = max_requests
        self._reserved = 0
        self._lock = asyncio.Lock()

    async def reserve(self) -> bool:
        async with self._lock:
            if self._reserved >= self.max_requests:
                return False
            self._reserved += 1
            return True


class KnodoWireMapper:
    """Map the four frozen semantic operations to one Knodo Bot Chat endpoint."""

    mode: Literal["knodo"] = "knodo"

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        targets: dict[Role, KnodoTarget],
        transport: Transport,
        budget: RequestBudget,
        stream_timeout_seconds: float = 300.0,
    ):
        self.base_url = _validate_origin(base_url)
        if not token:
            raise ValueError("Knodo token is required")
        if set(targets) != {"tutor", "designer"}:
            raise ValueError("both fixed Knodo targets are required")
        self._token = token
        self._targets = dict(targets)
        self._transport = transport
        self._budget = budget
        self._stream_timeout_seconds = stream_timeout_seconds

    async def aclose(self) -> None:
        closer = getattr(self._transport, "aclose", None)
        if closer is not None:
            await closer()

    def continuation_scope(self, operation: Operation, *, contract_version: str) -> str:
        """Identity of a remote conversation's safe reuse boundary.

        Changing role, Bot, workspace, wire profile, or local semantic contract
        creates a new scope, so an old conversation cannot be reused silently.
        """

        role = OPERATION_SPECS[operation].role
        target = self._targets[role]
        return (
            "knodo-bot-chat-v1"
            f"|contract={contract_version}"
            f"|role={role}"
            f"|workspace={target.workspace_id}"
            f"|bot={target.bot_id}"
        )

    async def invoke(
        self,
        operation: Operation,
        request: dict[str, Any],
        *,
        scenario: Any = None,
        timeout_seconds: float | None = None,
        cancel: asyncio.Event | None = None,
        delay_seconds: float | None = None,
        remote_conversation_id: str | None = None,
        on_content: Callable[[str], Awaitable[None]] | None = None,
    ) -> BackendOutcome:
        del scenario, delay_seconds  # fixture-only controls are never sent upstream
        target = self._targets[OPERATION_SPECS[operation].role]
        send_stream = getattr(self._transport, "send_stream", None)
        streaming = (
            on_content is not None
            and callable(send_stream)
            and operation in (Operation.TEACH_TURN, Operation.CODE_FEEDBACK)
        )
        try:
            mapped = self._map_request(
                operation,
                request,
                target=target,
                remote_conversation_id=remote_conversation_id,
                streaming=streaming,
            )
        except (TypeError, ValueError):
            return BackendOutcome(
                error=GatewayError(
                    GatewayErrorCategory.VALIDATION,
                    "KNODO_WIRE_REQUEST_INVALID",
                )
            )

        if cancel is not None and cancel.is_set():
            return BackendOutcome(cancelled=True)
        if not await self._budget.reserve():
            return BackendOutcome(
                error=GatewayError(
                    GatewayErrorCategory.RATE,
                    "LIVE_REQUEST_BUDGET_EXHAUSTED",
                )
            )

        if streaming:
            last_visible: str | None = None

            async def forward_wire_content(content: str) -> None:
                nonlocal last_visible
                visible = partial_top_level_string(content, "message_markdown")
                if visible is not None and visible != last_visible:
                    last_visible = visible
                    await on_content(visible)  # type: ignore[misc]

            outcome = await send_stream(
                mapped,
                timeout_seconds=self._stream_timeout_seconds,
                cancel=cancel,
                on_content=forward_wire_content,
            )
        else:
            outcome = await self._transport.send(
                mapped,
                timeout_seconds=timeout_seconds or 20.0,
                cancel=cancel,
            )
        if outcome.error is not None or outcome.cancelled:
            return outcome
        return self._parse_response(
            operation,
            target,
            outcome,
            expected_conversation_id=remote_conversation_id,
            streaming=streaming,
        )

    def _map_request(
        self,
        operation: Operation,
        request: dict[str, Any],
        *,
        target: KnodoTarget,
        remote_conversation_id: str | None,
        streaming: bool = False,
    ) -> UpstreamRequest:
        request_json = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content = f"{_protocol_instruction(operation)}\nREQUEST_JSON:\n{request_json}"
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": content}],
            "stream": streaming,
            # Select the server-bound workspace even when the Bot has another
            # source workspace. See https://knodo.vip/llms-full.txt (Bot Chat).
            "workspaceId": target.workspace_id,
            # Bot Chat defaults to bypassPermissions. Use the documented safer
            # mode explicitly so tool/file access is never silently elevated.
            "permissionMode": "default",
            "includeToolResults": False,
        }
        if remote_conversation_id is not None:
            if not _valid_conversation_id(remote_conversation_id):
                raise ValueError("invalid backend-owned conversation id")
            payload["conversationId"] = remote_conversation_id

        return UpstreamRequest(
            url=(
                f"{self.base_url}/api/v1/bots/{target.bot_id}/chat/completions"
                f"{'/stream' if streaming else ''}"
            ),
            payload=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            request_id=_local_request_id(operation, request),
        )

    def _parse_response(
        self,
        operation: Operation,
        target: KnodoTarget,
        outcome: BackendOutcome,
        *,
        expected_conversation_id: str | None,
        streaming: bool = False,
    ) -> BackendOutcome:
        wire = outcome.payload
        if not isinstance(wire, dict):
            return _invalid("KNODO_RESPONSE_SHAPE_INVALID", outcome.upstream_calls)
        choices = wire.get("choices")
        completion_id = wire.get("id")
        conversation_id = wire.get("conversationId")
        if streaming and conversation_id is None:
            # The public Knodo docs promise OpenAI-compatible SSE, but do not
            # promise the vendor conversation ID in every chunk. A known,
            # backend-owned continuation ID remains valid; a new conversation
            # without one simply cannot be reused on the next turn.
            conversation_id = expected_conversation_id
        model = wire.get("model")
        if (
            wire.get("object") != "chat.completion"
            or not isinstance(completion_id, str)
            or not completion_id
            or (conversation_id is None and not streaming)
            or (conversation_id is not None and not _valid_conversation_id(conversation_id))
            or not isinstance(model, str)
            or not model
            or not isinstance(choices, list)
            or not choices
            or not isinstance(choices[0], dict)
        ):
            return _invalid("KNODO_RESPONSE_SHAPE_INVALID", outcome.upstream_calls)
        if expected_conversation_id is not None and conversation_id != expected_conversation_id:
            return _invalid("KNODO_CONVERSATION_MISMATCH", outcome.upstream_calls)

        choice = choices[0]
        message = choice.get("message")
        finish_reason = choice.get("finish_reason")
        if (
            choice.get("index") != 0
            or not isinstance(message, dict)
            or message.get("role") != "assistant"
            or not isinstance(message.get("content"), str)
            or not isinstance(finish_reason, str)
        ):
            return _invalid("KNODO_RESPONSE_SHAPE_INVALID", outcome.upstream_calls)
        if finish_reason != "stop":
            metadata = _remote_metadata(
                operation=operation,
                target=target,
                wire=wire,
                completion_id=completion_id,
                conversation_id=conversation_id,
                model=model,
                finish_reason=finish_reason,
            )
            reason = (
                "KNODO_RESPONSE_REPORTED_ERROR"
                if finish_reason == "error"
                else "KNODO_RESPONSE_INCOMPLETE"
            )
            return _invalid(reason, outcome.upstream_calls, remote_metadata=metadata)

        metadata = _remote_metadata(
            operation=operation,
            target=target,
            wire=wire,
            completion_id=completion_id,
            conversation_id=conversation_id,
            model=model,
            finish_reason=finish_reason,
        )

        try:
            semantic = json.loads(message["content"])
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _invalid(
                "KNODO_ASSISTANT_CONTENT_NOT_JSON_OBJECT",
                outcome.upstream_calls,
                remote_metadata=metadata,
            )
        if not isinstance(semantic, dict):
            return _invalid(
                "KNODO_ASSISTANT_CONTENT_NOT_JSON_OBJECT",
                outcome.upstream_calls,
                remote_metadata=metadata,
            )
        return BackendOutcome(
            payload=semantic,
            upstream_calls=outcome.upstream_calls,
            remote_metadata=metadata,
        )


def _validate_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Knodo base URL must be a bare HTTPS origin")
    return value.rstrip("/")


def _local_request_id(operation: Operation, request: dict[str, Any]) -> str:
    value = request.get("request_id")
    if isinstance(value, str) and value:
        return value
    return operation.value


def _protocol_instruction(operation: Operation) -> str:
    common = (
        "只输出一个完整JSON对象，不要Markdown围栏或前后说明；"
        "不得调用工具、不得写文件、不得返回工具日志。"
    )
    if operation in (Operation.TEACH_TURN, Operation.CODE_FEEDBACK):
        return (
            f"{common} 顶层schema_version必须是k12.teaching.response.v1。"
            "action为OPEN_ANIMATION或OPEN_RESOURCE时只能使用resource_id字段，"
            "不得使用animation_id。所有字段必须严格符合已绑定的teaching-response.schema.json。"
        )
    if operation is Operation.QUIZ_DRAFT:
        return (
            f"{common} 顶层schema_version必须是k12.quiz.draft.v1；"
            "顶层只能包含schema_version、request_id、chapter_id、curriculum_revision、stage、"
            "difficulty、questions、warnings。每题使用question_key、objective_id、stem、"
            "explanation、hints、source_refs、type以及对应题型字段；hints必须是字符串数组。"
            'SINGLE_CHOICE的options必须是[{"key":"A","text":"..."}]对象数组，'
            "correct_answer必须是选项key字符串。不得输出question_id、answer_key、"
            "题内difficulty、misconception_focus、顶层objective_ids、quiz_spec或"
            "suggested_resource_id。所有字段必须严格符合已绑定的quiz-draft.schema.json。"
        )
    return (
        f"{common} 顶层schema_version必须是k12.lesson.package.draft.v1；"
        "所有字段必须严格符合已绑定的lesson-package-draft.schema.json。"
    )


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _remote_metadata(
    *,
    operation: Operation,
    target: KnodoTarget,
    wire: dict[str, Any],
    completion_id: str,
    conversation_id: str | None,
    model: str,
    finish_reason: str,
) -> dict[str, Any]:
    usage = wire.get("usage") if isinstance(wire.get("usage"), dict) else {}
    return {
        "provider": "knodo",
        "role": OPERATION_SPECS[operation].role,
        "bot_id": target.bot_id,
        "workspace_id": target.workspace_id,
        "completion_id": completion_id,
        "conversation_id": conversation_id,
        "model": model,
        "finish_reason": finish_reason,
        "prompt_tokens": _nonnegative_int(usage.get("prompt_tokens")),
        "completion_tokens": _nonnegative_int(usage.get("completion_tokens")),
        "total_tokens": _nonnegative_int(usage.get("total_tokens")),
    }


def _valid_conversation_id(value: Any) -> bool:
    # Official docs define this as a string but do not publish a character
    # grammar. Keep it opaque; reject only unsafe controls and unreasonable
    # size rather than guessing a provider-specific identifier format.
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 256
        and all(ord(character) >= 0x20 and character != "\x7f" for character in value)
    )


def _invalid(
    reason: str,
    upstream_calls: int,
    *,
    remote_metadata: dict[str, Any] | None = None,
) -> BackendOutcome:
    return BackendOutcome(
        error=GatewayError(GatewayErrorCategory.VALIDATION, reason),
        upstream_calls=upstream_calls,
        remote_metadata=remote_metadata,
    )


__all__ = [
    "InMemoryRequestBudget",
    "KnodoTarget",
    "KnodoWireMapper",
    "RequestBudget",
]
