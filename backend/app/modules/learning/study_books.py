"""Resolve the same packaged Markdown read by the student book reader."""

import hashlib
import re
from functools import lru_cache
from pathlib import Path

_BOOKS = {"python3", "ai-agent", "vibe-coding"}
_DIRECTORY = Path(__file__).resolve().parents[4] / "frontend/src/features/books/content"


@lru_cache(maxsize=3)
def book_sections(slug):
    if slug not in _BOOKS:
        raise ValueError("教材不存在")
    data = (_DIRECTORY / f"{slug}.md").read_bytes()
    parts = re.split(r"(?m)^## ", data.decode("utf-8"))[1:]
    return hashlib.sha256(data).hexdigest(), parts


def bind_book_scene(scene):
    version, sections = book_sections(scene.get("content_id"))
    index = scene.get("section_index")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(sections):
        raise ValueError("教材位置无效")
    if scene.get("content_version") != version:
        raise ValueError("教材版本已变化，请刷新后提问")
    title, _, body = sections[index].partition("\n")
    selected = scene.get("selected_text") or ""
    return {
        **scene,
        "visible_section": title.strip()[:200],
        "selected_text": selected if selected and selected in body else body.strip()[:4000],
        "knowledge_points": [title.strip()[:160]],
    }
