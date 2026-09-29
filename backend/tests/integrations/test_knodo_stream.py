"""Real SSE wire decoding without live credentials or network calls."""

from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.knodo.operations import Operation
from app.integrations.knodo.partial import partial_top_level_string
from app.integrations.knodo.transport import HttpTransport
from app.integrations.knodo.wire import InMemoryRequestBudget, KnodoTarget, KnodoWireMapper
from app.modules.teaching.validation import safe_partial_markdown


def _event(piece: str = "", finish: str | None = None, *, with_conversation_id: bool = True) -> str:
    payload = {
        "id": "chatcmpl-stream-test",
        "object": "chat.completion.chunk",
        "model": "synthetic-model",
        "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": finish}],
    }
    if with_conversation_id:
        payload["conversationId"] = "conv_stream_test"
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("remote_conversation_id", [None, "conv_stream_test"])
async def test_knodo_teaching_stream_extracts_only_markdown_from_json(
    remote_conversation_id: str | None,
):
    seen_request: list[tuple[str, dict]] = []
    semantic = {
        "schema_version": "k12.teaching.response.v1",
        "message_markdown": "先看这一步，再自己试一试。",
        "source_refs": [{"source_id": "private-source-marker"}],
    }
    wire_content = json.dumps(semantic, ensure_ascii=False)
    pieces = [wire_content[index : index + 7] for index in range(0, len(wire_content), 7)]
    sse = "".join(_event(piece) for piece in pieces) + _event(finish="stop") + "data: [DONE]\n\n"

    def respond(request: httpx.Request) -> httpx.Response:
        seen_request.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    mapper = KnodoWireMapper(
        base_url="https://knodo.example.invalid",
        token="synthetic-credential",
        targets={
            "tutor": KnodoTarget(bot_id="tutor-test", workspace_id="workspace-test"),
            "designer": KnodoTarget(bot_id="designer-test", workspace_id="workspace-test"),
        },
        transport=HttpTransport(client, max_output_bytes=262144),
        budget=InMemoryRequestBudget(1),
    )
    drafts: list[str] = []

    async def capture(text: str) -> None:
        drafts.append(text)

    outcome = await mapper.invoke(
        Operation.TEACH_TURN,
        {"request_id": "synthetic", "conversationId": "learner-controlled-id"},
        remote_conversation_id=remote_conversation_id,
        on_content=capture,
    )
    await mapper.aclose()

    assert len(seen_request) == 1
    url, sent = seen_request[0]
    assert url == "https://knodo.example.invalid/api/v1/bots/tutor-test/chat/completions/stream"
    assert sent["stream"] is True
    assert sent["workspaceId"] == "workspace-test"
    assert sent.get("conversationId") == remote_conversation_id
    assert outcome.error is None
    assert outcome.payload == semantic
    assert drafts[-1] == semantic["message_markdown"]
    assert all("private-source-marker" not in draft for draft in drafts)
    assert all("schema_version" not in draft for draft in drafts)


@pytest.mark.asyncio
async def test_openai_compatible_chunks_without_vendor_conversation_id_still_complete():
    semantic = {"message_markdown": "逐步解释即可。"}
    sse = (
        _event(json.dumps(semantic, ensure_ascii=False), with_conversation_id=False)
        + _event(finish="stop", with_conversation_id=False)
        + "data: [DONE]\n\n"
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse)
        )
    )
    mapper = KnodoWireMapper(
        base_url="https://knodo.example.invalid",
        token="synthetic-credential",
        targets={
            "tutor": KnodoTarget(bot_id="tutor-test", workspace_id="workspace-test"),
            "designer": KnodoTarget(bot_id="designer-test", workspace_id="workspace-test"),
        },
        transport=HttpTransport(client, max_output_bytes=4096),
        budget=InMemoryRequestBudget(1),
    )

    async def noop(_: str) -> None:
        return None

    outcome = await mapper.invoke(
        Operation.TEACH_TURN, {"request_id": "synthetic"}, on_content=noop
    )
    await mapper.aclose()
    assert outcome.error is None
    assert outcome.payload == semantic
    assert outcome.remote_metadata["conversation_id"] is None


@pytest.mark.asyncio
async def test_stream_request_accepts_one_nonstream_json_response_without_retry():
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"object": "chat.completion", "choices": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    transport = HttpTransport(client, max_output_bytes=4096)
    from app.integrations.knodo.transport import UpstreamRequest

    async def noop(_: str) -> None:
        return None

    outcome = await transport.send_stream(
        UpstreamRequest(
            url="https://knodo.example.invalid/test",
            payload={"stream": True},
            headers={},
            request_id="synthetic",
        ),
        timeout_seconds=2,
        on_content=noop,
    )
    await transport.aclose()
    assert calls == 1
    assert outcome.payload == {"object": "chat.completion", "choices": []}


@pytest.mark.asyncio
async def test_many_small_deltas_do_not_exhaust_decoded_content_budget():
    content = json.dumps({"message_markdown": "答" * 1200}, ensure_ascii=False)
    sse = "".join(_event(char) for char in content) + _event(finish="stop") + "data: [DONE]\n\n"
    assert len(sse.encode("utf-8")) > 8192  # frame overhead exceeds decoded output
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse)
        )
    )
    transport = HttpTransport(client, max_output_bytes=8192)
    from app.integrations.knodo.transport import UpstreamRequest

    observed_lengths: list[int] = []

    async def capture(accumulated: str) -> None:
        observed_lengths.append(len(accumulated))

    outcome = await transport.send_stream(
        UpstreamRequest(
            url="https://knodo.example.invalid/test",
            payload={"stream": True},
            headers={},
            request_id="synthetic",
        ),
        timeout_seconds=3,
        on_content=capture,
    )
    await transport.aclose()
    assert outcome.error is None
    assert outcome.payload["choices"][0]["message"]["content"] == content
    assert observed_lengths[-1] == len(content)


@pytest.mark.asyncio
async def test_stream_without_done_is_not_treated_as_success():
    sse = _event('{"message_markdown":"不完整')
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse)
        )
    )
    transport = HttpTransport(client, max_output_bytes=4096)
    from app.integrations.knodo.transport import UpstreamRequest

    async def noop(_: str) -> None:
        return None

    outcome = await transport.send_stream(
        UpstreamRequest(
            url="https://knodo.example.invalid/test",
            payload={"stream": True},
            headers={},
            request_id="synthetic",
        ),
        timeout_seconds=2,
        on_content=noop,
    )
    await transport.aclose()
    assert outcome.error is not None
    assert outcome.error.reason_code == "UPSTREAM_STREAM_INCOMPLETE"
    assert outcome.upstream_calls == 1


@pytest.mark.asyncio
async def test_knodo_terminal_chunk_without_done_is_complete():
    """Knodo ends a clean stream after stop and may omit [DONE]."""

    content = '{"message_markdown":"你好"}'
    first = _event(content, with_conversation_id=False)
    final_frame = {
        "id": "chatcmpl-stream-test",
        "object": "chat.completion.chunk",
        "model": "synthetic-model",
        "conversationId": "conv_stream_test",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    sse = first + f"data: {json.dumps(final_frame)}\n\n"
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(201, headers={"content-type": "text/event-stream"}, text=sse)
        )
    )
    transport = HttpTransport(client, max_output_bytes=4096)
    from app.integrations.knodo.transport import UpstreamRequest

    observed: list[str] = []

    async def capture(accumulated: str) -> None:
        observed.append(accumulated)

    outcome = await transport.send_stream(
        UpstreamRequest(
            url="https://knodo.example.invalid/test",
            payload={"stream": True},
            headers={},
            request_id="synthetic",
        ),
        timeout_seconds=2,
        on_content=capture,
    )
    await transport.aclose()
    assert outcome.error is None
    assert outcome.payload["choices"][0]["message"]["content"] == content
    assert outcome.payload["conversationId"] == "conv_stream_test"
    assert observed == [content]


def test_partial_extractor_ignores_nested_and_escaped_keys_and_split_surrogates():
    document = (
        '{"other":{"message_markdown":"hidden"},'
        '"quoted":"\\"message_markdown\\":\\"hidden\\"",'
        '"message_markdown":"你好\\ud83d'
    )
    assert partial_top_level_string(document, "message_markdown") == "你好"
    assert partial_top_level_string(document + '\\ude00！"}', "message_markdown") == "你好😀！"


def test_partial_filter_holds_split_forbidden_marker():
    marker = "correct_answer"
    prefix = "这是解释。"
    for index in range(1, len(marker)):
        visible = safe_partial_markdown(prefix + marker[:index], max_chars=1200)
        assert visible is not None
        assert marker[:index] not in visible
    assert safe_partial_markdown(prefix + marker, max_chars=1200) is None
