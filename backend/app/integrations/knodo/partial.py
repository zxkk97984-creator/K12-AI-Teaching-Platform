"""Extract a provisional top-level JSON string without exposing wire JSON.

Knodo streams the assistant's *structured* JSON as text deltas. Only the
``message_markdown`` value is suitable for a provisional teaching bubble; the
other fields (sources, actions, identifiers) remain private until validation.
"""

from __future__ import annotations

import json


def partial_top_level_string(document: str, field: str) -> str | None:
    depth = 0
    in_string = False
    escaped = False
    expect_key = False
    key_start: int | None = None
    for index, char in enumerate(document):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                if key_start is not None:
                    try:
                        key = json.loads(document[key_start : index + 1])
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        return None
                    key_start = None
                    if key == field:
                        cursor = index + 1
                        while cursor < len(document) and document[cursor].isspace():
                            cursor += 1
                        if cursor >= len(document) or document[cursor] != ":":
                            return None
                        cursor += 1
                        while cursor < len(document) and document[cursor].isspace():
                            cursor += 1
                        if cursor >= len(document) or document[cursor] != '"':
                            return None
                        return _decode_string_prefix(document[cursor + 1 :])
            continue
        if char == '"':
            in_string = True
            if depth == 1 and expect_key:
                key_start = index
                expect_key = False
        elif char in "{[":
            depth += 1
            if depth == 1:
                expect_key = True
        elif char in "}]":
            depth -= 1
            if depth < 0:
                return None
        elif char == "," and depth == 1:
            expect_key = True
    return None


def _decode_string_prefix(raw: str) -> str | None:
    result: list[str] = []
    cursor = 0
    escapes = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while cursor < len(raw):
        char = raw[cursor]
        if char == '"':
            return "".join(result)
        if char != "\\":
            if ord(char) < 32:
                return None
            result.append(char)
            cursor += 1
            continue
        if cursor + 1 >= len(raw):
            break
        code = raw[cursor + 1]
        if code != "u":
            if code not in escapes:
                return None
            result.append(escapes[code])
            cursor += 2
            continue
        if cursor + 6 > len(raw):
            break
        try:
            point = int(raw[cursor + 2 : cursor + 6], 16)
        except ValueError:
            return None
        if 0xD800 <= point <= 0xDBFF:
            if cursor + 12 > len(raw):
                break
            if raw[cursor + 6 : cursor + 8] != "\\u":
                return None
            try:
                low = int(raw[cursor + 8 : cursor + 12], 16)
            except ValueError:
                return None
            if not 0xDC00 <= low <= 0xDFFF:
                return None
            result.append(chr(0x10000 + (point - 0xD800) * 1024 + low - 0xDC00))
            cursor += 12
        elif 0xDC00 <= point <= 0xDFFF:
            return None
        else:
            result.append(chr(point))
            cursor += 6
    return "".join(result)
