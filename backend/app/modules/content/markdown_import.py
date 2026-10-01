"""Convert the supplied computing lectures into reproducible curriculum packages.

Only headings outside fenced examples establish chapter boundaries. Original
bytes are archived by hash; normalized Markdown remains the editable source.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.modules.content.package import canonical_json

BASE_KEY = "computing-ai-md-v1"
STAGES = {"PRIMARY_LOWER": (1, 3), "PRIMARY_UPPER": (4, 6), "JUNIOR": (7, 9), "SENIOR": (10, 12)}
META = {"目录", "章节列表", "本书简介", "内容来源说明", "原书信息"}
# (slug, title, files, split rule). File numbering is not used as an identity.
COURSES = [
    ("primary-ai", "人工智能启蒙", ["小学/01-人工智能启蒙.md"], "h2"),
    ("primary-scratch", "Scratch 少儿趣味编程", ["小学/02-Scratch少儿趣味编程.md"], "h2"),
    ("primary-computer", "电脑入门", ["小学/03-中小学生电脑入门.md"], "h2"),
    ("primary-safety", "儿童网络安全", ["小学/04-网络安全自助指南.md"], "h2"),
    ("primary-unplugged", "不插电的计算机科学", ["小学/05-不插电的计算机科学.md"], "h2"),
    (
        "junior-python",
        "Python 编程：从入门到实践",
        ["初中/01-Python编程从入门到实践.md"],
        "chapter",
    ),
    ("junior-algorithms", "算法图解", ["初中/02-算法图解.md"], "chapter"),
    ("junior-coding", "编码与计算机原理", ["初中/04-编码.md", "初中/03-编码.md"], "coding"),
    ("junior-ml", "图解机器学习", ["初中/04-图解机器学习.md"], "h1"),
    ("junior-network", "网络是怎样连接的", ["初中/05-网络是怎样连接的.md"], "chapter"),
    ("senior-pathways", "学习路径与综合实践", ["高中/00-学段总览与补充板块.md"], "h2"),
    ("senior-python", "Python 进阶", ["高中/01-流畅的Python.md"], "chapter"),
    ("senior-data-structures", "数据结构", ["高中/02-大话数据结构.md"], "h2"),
    ("senior-algorithms", "算法竞赛入门", ["高中/02-算法竞赛入门经典.md"], "h2"),
    ("senior-deep-learning", "动手学深度学习", ["高中/03-动手学深度学习.md"], "h2"),
    ("senior-olympiad", "信息学奥赛基础与实践", ["高中/04-信息学奥赛一本通.md"], "h3"),
    ("senior-ml", "机器学习实战", ["高中/05-机器学习实战.md"], "h3"),
    ("senior-coding", "编码与计算机系统", ["高中/07-编码.md"], "h2"),
    ("senior-network", "计算机网络", ["高中/08-计算机网络自顶向下方法.md"], "h2"),
    ("senior-systems", "计算机系统与软件实践", ["高中/09-深入理解计算机系统.md"], "systems"),
]
LOWER = {
    "primary-ai": {1, 2, 3, 4, 5, 6, 10, 11, 14},
    "primary-scratch": {1, 2, 3},
    "primary-computer": {1, 2},
    "primary-safety": {1, 2, 3, 5, 10, 11, 12},
    "primary-unplugged": {1, 4, 5, 8, 9},
}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_markdown(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    # Broken local TOC links are replaced by the platform's course navigation.
    text = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+\.md(?:#[^)]*)?)\)", r"\1", text)
    text = text.replace(
        "Python 3.7+ dict 保留插入顺序，但这不应该被当作语义依赖",
        "Python 3.7 起，dict 保留插入顺序是语言保证；set 不保证插入顺序",
    )
    text = text.replace(
        "| 图 | — | 取决于表示 | 邻接表/矩阵 | 社交网络、地图 |",
        "| 图 | — | 取决于表示 | 取决于表示 | 取决于表示 | 社交网络、地图 |",
    )
    return text.strip() + "\n"


def headings(text: str) -> list[tuple[int, int, str]]:
    result = []
    fence = None
    for index, line in enumerate(text.splitlines(keepends=True)):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)[0]
            elif marker.group(1)[0] == fence:
                fence = None
            continue
        if fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            result.append((index, len(match.group(1)), match.group(2)))
    return result


def clean_title(title: str) -> str:
    return re.sub(r"^\d{2}-", "", title).strip()


def sections(text: str, rule: str) -> list[tuple[str, str]]:
    lines = text.splitlines(keepends=True)
    all_heads = headings(text)
    matches = []
    for position, (index, level, title) in enumerate(all_heads):
        if position == 0 or title in META:
            continue
        is_chapter = bool(re.match(r"第\s*\d+", title))
        selected = (
            (rule == "h2" and level == 2)
            or (rule == "h3" and level == 3)
            or (rule == "h1" and level == 1)
            or (rule in {"chapter", "coding"} and is_chapter)
            or (rule == "chapter" and level == 2 and title.startswith(("附录", "补充")))
            or (rule == "systems" and (level == 2 or (level == 3 and title.startswith("3."))))
        )
        if selected:
            matches.append((index, title))
    if not matches:
        raise ValueError(f"No chapters found for split rule {rule}")
    preamble = "".join(lines[1 : matches[0][0]]).strip()
    result = []
    for position, (index, title) in enumerate(matches):
        end = matches[position + 1][0] if position + 1 < len(matches) else len(lines)
        body = "".join(lines[index + 1 : end]).strip()
        if position == 0 and preamble:
            body = preamble + "\n\n" + body
        if not body:
            raise ValueError(f"Empty chapter: {title}")
        result.append((clean_title(title), body))
    return result


def markdown_blocks(text: str) -> list[dict[str, str]]:
    """Pack complete paragraphs and fenced examples into bounded Markdown blocks."""
    units, pending = [], []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)[0]
            elif marker.group(1)[0] == fence:
                fence = None
        pending.append(line)
        if not line.strip() and fence is None:
            units.append("".join(pending).strip())
            pending = []
    if fence:
        raise ValueError("Unclosed Markdown code fence")
    if pending:
        units.append("".join(pending).strip())
    blocks, current = [], ""
    for unit in filter(None, units):
        if len(unit) > 4000:
            raise ValueError("A complete Markdown unit exceeds 4000 characters")
        if current and len(current) + len(unit) + 2 > 4000:
            blocks.append({"type": "MARKDOWN", "text": current})
            current = ""
        current = f"{current}\n\n{unit}".strip()
    if current:
        blocks.append({"type": "MARKDOWN", "text": current})
    return blocks


def convert_markdown(source_dir: Path, output_dir: Path) -> dict:
    original = {}
    inventory = {}
    for path in sorted(source_dir.rglob("*.md")):
        relative = path.relative_to(source_dir).as_posix()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        archive = f"sources/{digest[:16]}/{path.name}"
        target = output_dir / archive
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("Original source hash collision")
        target.write_bytes(raw)
        original[relative] = normalize_markdown(raw.decode("utf-8-sig"))
        inventory[relative] = {"sha256": digest, "archive": archive}
    course_files, chapters_count = [], 0
    for slug, title, files, rule in COURSES:
        for filename in files:
            if filename not in original:
                raise ValueError(f"Missing supplied lecture: {filename}")
        text = original[files[0]]
        parts = sections(text, rule)
        source_file = files[0]
        if rule == "coding":
            supplements = sections(original[files[1]], "h1")
            for supplement_title, body in supplements:
                keyword = (
                    "进制"
                    if "二进制" in supplement_title
                    else "Unicode"
                    if "字符" in supplement_title
                    else None
                )
                found = next(
                    (i for i, (name, _) in enumerate(parts) if keyword and keyword in name), None
                )
                if found is None:
                    parts.append((supplement_title, body))
                else:
                    name, existing = parts[found]
                    parts[found] = (name, existing + "\n\n### 补充讲解\n\n" + body)
            combined = "\n\n".join(
                (source_dir / name).read_text(encoding="utf-8") for name in files
            )
            raw = combined.encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            source_file = "初中/编码合并来源.md"
            archive = f"sources/{digest[:16]}/编码合并来源.md"
            (output_dir / archive).parent.mkdir(parents=True, exist_ok=True)
            (output_dir / archive).write_bytes(raw)
            inventory[source_file] = {"sha256": digest, "archive": archive}
        normalized = output_dir / "normalized" / f"{slug}.md"
        normalized.parent.mkdir(parents=True, exist_ok=True)
        normalized.write_text(
            "# "
            + title
            + "\n\n"
            + "\n\n".join("## " + name + "\n\n" + body for name, body in parts)
            + "\n",
            encoding="utf-8",
        )
        course_path = output_dir / "courses" / slug / "course.json"
        old = json.loads(course_path.read_text()) if course_path.exists() else {"chapters": []}
        old_chapters = {item["stable_slug"]: item for item in old["chapters"]}
        specs, points = [], []
        for number, (name, body) in enumerate(parts, 1):
            point = f"{slug}-topic-{number:02}"
            points.append(
                {
                    "slug": point,
                    "name": name[:200],
                    "topic": "计算机与人工智能",
                    "description": f"学习并解释「{name}」中的核心概念与示例。",
                }
            )
            stages = (
                ["PRIMARY_UPPER"]
                if slug.startswith("primary-")
                else ["JUNIOR" if slug.startswith("junior-") else "SENIOR"]
            )
            if number in LOWER.get(slug, set()):
                stages.insert(0, "PRIMARY_LOWER")
            for stage in stages:
                band = {"PRIMARY_LOWER": "lower", "PRIMARY_UPPER": "upper"}.get(stage, "main")
                chapter_slug = f"ch-{number:03}-{band}"
                previous = old_chapters.get(chapter_slug)
                blocks = [
                    {"type": "TITLE", "text": name},
                    {
                        "type": "PARAGRAPH",
                        "text": f"本节学习：{name}。讲义保留原有示例与练习，可结合正文向教师提问。",
                    },
                    *markdown_blocks(body),
                ]
                revision = previous["revision"] if previous else 1
                source = {
                    "source_commit": None,
                    "source_path": inventory[source_file]["archive"],
                    "original_sha256": inventory[source_file]["sha256"],
                    "conversion": "supplied-markdown-v1",
                }
                if previous:
                    old_body = json.loads(
                        (course_path.parent / previous["content_file"]).read_text()
                    )
                    if old_body["blocks"] != blocks or previous["source"] != source:
                        revision += 1
                content_file = f"chapters/{chapter_slug}-r{revision}.json"
                write_json(
                    course_path.parent / content_file,
                    {
                        "schema_version": "k12.content.chapter-blocks.v1",
                        "chapter": chapter_slug,
                        "revision": revision,
                        "blocks": blocks,
                        "observed_knowledge_point_marks": [point],
                    },
                )
                low, high = STAGES[stage]
                specs.append(
                    {
                        "stable_slug": chapter_slug,
                        "revision": revision,
                        "order_index": number * 2 + (stage == "PRIMARY_UPPER"),
                        "title": name,
                        "stage": stage,
                        "grade_min": low,
                        "grade_max": high,
                        "objectives": [f"解释「{name}」的主要概念，并结合示例完成文中练习。"],
                        "knowledge_points": [point],
                        "license_code": "UNKNOWN",
                        "license_notes": "用户提供的参考书整理讲义；原书信息见正文。",
                        "source": source,
                        "content_file": content_file,
                    }
                )
        course = {
            "schema_version": "k12.content.course.v1",
            "stable_slug": slug,
            "title": title,
            "topic": "计算机与人工智能",
            "description": (
                f"按章节学习{title}，保留参考讲义的讲解、示例和练习，支持阅读续学与教师提问。"
            ),
            "knowledge_points": points,
            "chapters": specs,
        }
        write_json(course_path, course)
        course_files.append(f"courses/{slug}/course.json")
        chapters_count += len(specs)
    fingerprint = hashlib.sha256(
        canonical_json(
            [json.loads((output_dir / path).read_text()) for path in course_files]
        ).encode()
    ).hexdigest()[:12]
    write_json(
        output_dir / "release.json",
        {
            "schema_version": "k12.content.release.v1",
            "release_key": f"{BASE_KEY}-{fingerprint}",
            "source_kind": "NEW_SOURCE",
            "is_test_fixture": False,
            "local_demo_visible": True,
            "description": "用户提供的计算机与人工智能 Markdown 学习讲义，按四学段章节整理。",
            "license_code": "UNKNOWN",
            "license_notes": "参考书整理内容；来源说明和原文件哈希随课程保存。",
            "course_files": course_files,
        },
    )
    write_json(
        output_dir / "inventory.json",
        {"originals": inventory, "courses": len(course_files), "chapter_versions": chapters_count},
    )
    return {
        "courses": len(course_files),
        "chapter_versions": chapters_count,
        "release_key": f"{BASE_KEY}-{fingerprint}",
    }
