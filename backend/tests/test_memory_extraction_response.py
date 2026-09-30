import json

import pytest

from app.modules.ai.extraction import parse_extraction_response


def _body(request_id: str) -> str:
    return json.dumps(
        {
            "schema_version": "k12.memory.extract.response.v1",
            "request_id": request_id,
            "facts": [
                {
                    "key": "interest:stargazing",
                    "category": "INTEREST",
                    "statement": "喜欢观察星星",
                    "source_message_id": "source-1",
                    "quote": "我喜欢观察星星。",
                    "certainty": "EXPLICIT",
                    "valid_until": None,
                }
            ],
            "summaries": [],
        },
        ensure_ascii=False,
    )


def test_parses_knodo_json_code_fence():
    parsed = parse_extraction_response(f"```json\n{_body('request-1')}\n```", "request-1")

    assert parsed.facts[0].source_message_id == "source-1"
    assert parsed.request_id == "request-1"


def test_parses_plain_json():
    parsed = parse_extraction_response(_body("request-2"), "request-2")

    assert parsed.facts[0].quote == "我喜欢观察星星。"


def test_rejects_prose_around_json_and_mismatched_request_id():
    with pytest.raises(ValueError):
        parse_extraction_response(f"结果如下：\n```json\n{_body('request-3')}\n```", "request-3")

    with pytest.raises(ValueError):
        parse_extraction_response(_body("other-request"), "request-4")
