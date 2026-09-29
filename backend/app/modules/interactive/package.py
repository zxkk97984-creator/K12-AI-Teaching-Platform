"""Validate offline activity packages and build an isolated self-contained document."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import posixpath
import stat
import unicodedata
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import tinycss2
from bs4 import BeautifulSoup
from bs4.element import Tag
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA = "k12-interactive-v1"
ALLOWED_EXTENSIONS = {
    ".html",
    ".css",
    ".js",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".mp3",
    ".ogg",
    ".wav",
    ".woff",
    ".woff2",
}
MAX_FILES = 500
MAX_EXPANDED = 100 * 1024 * 1024
MAX_PROMPTS = 100
CSP = (
    "default-src 'none'; script-src 'unsafe-inline' data:; "
    "style-src 'unsafe-inline' data:; img-src data:; media-src data:; "
    "font-src data:; connect-src 'none'; worker-src 'none'; "
    "frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'"
)


class PackageError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=1000)


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    scene_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    text: str = Field(min_length=2, max_length=500)
    trigger: str = Field(default="MANUAL", pattern=r"^(SCENE_ENTER|ACTIVITY_COMPLETE|MANUAL)$")
    audio: str | None = Field(default=None, max_length=300)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(pattern=r"^k12-interactive-v1$")
    content_key: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(pattern=r"^(LESSON|GAME|EXPERIMENT)$")
    stage: str = Field(pattern=r"^(PRIMARY_LOWER|PRIMARY_UPPER|JUNIOR|SENIOR)$")
    subject: str = Field(min_length=1, max_length=80)
    entry: str = Field(default="index.html", max_length=300)
    cover: str | None = Field(default=None, max_length=300)
    summary: str = Field(default="", max_length=1000)
    knowledge_points: list[str] = Field(default_factory=list, max_length=12)
    capabilities: list[str] = Field(default_factory=list, max_length=3)
    scenes: list[SceneSpec] = Field(default_factory=list, min_length=1, max_length=100)
    prompts: list[PromptSpec] = Field(default_factory=list, max_length=MAX_PROMPTS)

    @model_validator(mode="after")
    def references(self):
        scene_ids = [scene.id for scene in self.scenes]
        prompt_ids = [prompt.id for prompt in self.prompts]
        if len(set(scene_ids)) != len(scene_ids) or len(set(prompt_ids)) != len(prompt_ids):
            raise ValueError("场景或问题 ID 重复")
        if any(prompt.scene_id not in scene_ids for prompt in self.prompts):
            raise ValueError("问题引用了不存在的场景")
        automatic = [
            (prompt.scene_id, prompt.trigger)
            for prompt in self.prompts
            if prompt.trigger == "SCENE_ENTER"
        ]
        if len(automatic) != len(set(automatic)):
            raise ValueError("每个场景只能有一个进入时自动朗读的问题")
        if any(cap not in {"SCENES", "CHECKPOINTS", "COMPLETION"} for cap in self.capabilities):
            raise ValueError("存在未知接入能力")
        return self


def safe_name(name: str) -> str:
    decoded = unicodedata.normalize("NFC", unquote(name))
    if (
        not decoded
        or len(decoded) > 300
        or decoded.startswith("/")
        or "\\" in decoded
        or any(ord(character) < 32 or ord(character) == 127 for character in decoded)
        or any(character in decoded for character in "?#:%")
    ):
        raise PackageError("INTERACTIVE_PATH_INVALID", f"素材路径无效：{name[:100]}")
    path = PurePosixPath(decoded)
    if any(part in {"..", "."} for part in decoded.split("/")) or not path.parts:
        raise PackageError("INTERACTIVE_PATH_INVALID", f"素材路径无效：{name[:100]}")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise PackageError("INTERACTIVE_FILE_TYPE", f"不支持的文件类型：{name[:100]}")
    return str(path)


def _safe_manifest_path(name: str, files: dict[str, bytes], *, ext: str | None = None) -> str:
    path = safe_name(name)
    if path not in files or (ext and PurePosixPath(path).suffix.lower() != ext):
        raise PackageError("INTERACTIVE_FILE_MISSING", f"内容包缺少文件：{name}")
    return path


def read_package(
    raw: bytes, filename: str, *, default: dict[str, str]
) -> tuple[dict[str, bytes], Manifest]:
    if len(raw) > 20 * 1024 * 1024:
        raise PackageError("INTERACTIVE_TOO_LARGE", "内容包超过 20 MB")
    if filename.lower().endswith(".html"):
        files = {"index.html": raw}
        slug = default.get("slug", "interactive")
        manifest_data: dict[str, Any] = {
            "schema_version": SCHEMA,
            "content_key": slug,
            "title": default.get("title") or slug,
            "purpose": default.get("purpose"),
            "stage": default.get("stage"),
            "subject": default.get("subject"),
            "entry": "index.html",
            "summary": default.get("summary", ""),
            "scenes": [{"id": "main", "title": "主要内容", "summary": default.get("summary", "")}],
            "prompts": [],
            "capabilities": [],
        }
    elif filename.lower().endswith(".zip"):
        files = {}
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                if len(members) > MAX_FILES:
                    raise PackageError("INTERACTIVE_TOO_MANY_FILES", "文件数量超过上限")
                if sum(item.file_size for item in members) > MAX_EXPANDED:
                    raise PackageError("INTERACTIVE_EXPANDED_TOO_LARGE", "解压后体积超过上限")
                expanded = 0
                for item in members:
                    name = safe_name(item.filename)
                    if name in files:
                        raise PackageError("INTERACTIVE_DUPLICATE_PATH", f"文件路径重复：{name}")
                    if stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK:
                        raise PackageError("INTERACTIVE_SYMLINK", "内容包不能包含符号链接")
                    data = archive.read(item)
                    expanded += len(data)
                    if expanded > MAX_EXPANDED:
                        raise PackageError("INTERACTIVE_EXPANDED_TOO_LARGE", "解压后体积超过上限")
                    files[name] = data
        except (zipfile.BadZipFile, RuntimeError) as caught:
            raise PackageError("INTERACTIVE_ZIP_INVALID", "ZIP 无法读取") from caught
        if "manifest.json" not in files:
            raise PackageError("INTERACTIVE_MANIFEST_MISSING", "ZIP 缺少 manifest.json")
        try:
            manifest_data = json.loads(files["manifest.json"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as caught:
            raise PackageError("INTERACTIVE_MANIFEST_INVALID", "manifest.json 格式无效") from caught
        if not isinstance(manifest_data, dict):
            raise PackageError("INTERACTIVE_MANIFEST_INVALID", "manifest.json 必须是对象")
        if manifest_data.get("stage") != default.get("stage") or manifest_data.get(
            "purpose"
        ) != default.get("purpose"):
            raise PackageError("INTERACTIVE_STAGE_CONFLICT", "内容包学段或用途与登记信息不一致")
    else:
        raise PackageError("INTERACTIVE_FILE_TYPE", "请选择 .html 或 .zip")
    try:
        manifest = Manifest.model_validate(manifest_data)
    except ValidationError as caught:
        raise PackageError(
            "INTERACTIVE_MANIFEST_INVALID", str(caught.errors()[0].get("msg", "清单无效"))
        ) from caught
    _safe_manifest_path(manifest.entry, files, ext=".html")
    if manifest.cover:
        _safe_manifest_path(manifest.cover, files)
    for prompt in manifest.prompts:
        if prompt.audio:
            audio = _safe_manifest_path(prompt.audio, files)
            if PurePosixPath(audio).suffix.lower() not in {".mp3", ".ogg", ".wav"}:
                raise PackageError("INTERACTIVE_AUDIO_TYPE", "问题音频格式不支持")
    return files, manifest


def _data_uri(name: str, data: bytes) -> str:
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if name.endswith(".js"):
        mime = "text/javascript"
    if name.endswith(".svg"):
        mime = "image/svg+xml"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _asset_ref(ref: str, *, base: str, files: dict[str, bytes]) -> str:
    if ref.startswith("#") or ref.startswith("data:"):
        return ref
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc or ref.startswith("/") or parsed.query:
        raise PackageError("INTERACTIVE_EXTERNAL_ASSET", f"仅支持包内离线素材：{ref[:100]}")
    normalized = posixpath.normpath(posixpath.join(base, unquote(parsed.path)))
    name = safe_name(normalized)
    if name not in files:
        raise PackageError("INTERACTIVE_FILE_MISSING", f"引用的素材不存在：{ref[:100]}")
    return _data_uri(name, files[name]) + (f"#{parsed.fragment}" if parsed.fragment else "")


def _css_values(values: list, *, base: str, files: dict[str, bytes]) -> None:
    for token in values:
        if token.type == "url":
            token.representation = f'url("{_asset_ref(token.value, base=base, files=files)}")'
        elif token.type == "function" and token.lower_name == "url":
            raw = tinycss2.serialize(token.arguments).strip().strip("\"'")
            token.arguments = tinycss2.parse_component_value_list(
                f'"{_asset_ref(raw, base=base, files=files)}"'
            )
        elif hasattr(token, "content") and isinstance(token.content, list):
            _css_values(token.content, base=base, files=files)
        elif hasattr(token, "arguments") and isinstance(token.arguments, list):
            _css_values(token.arguments, base=base, files=files)


def _rewrite_css(css: str, *, base: str, files: dict[str, bytes]) -> str:
    nodes = tinycss2.parse_stylesheet(css, skip_comments=False, skip_whitespace=False)
    for node in nodes:
        if node.type == "at-rule" and node.lower_at_keyword == "import":
            raise PackageError("INTERACTIVE_CSS_IMPORT", "CSS @import 请合并到本地样式文件")
        if node.type == "error":
            raise PackageError("INTERACTIVE_CSS_INVALID", "CSS 语法无效")
        if hasattr(node, "content") and isinstance(node.content, list):
            _css_values(node.content, base=base, files=files)
        if hasattr(node, "prelude") and isinstance(node.prelude, list):
            _css_values(node.prelude, base=base, files=files)
    return tinycss2.serialize(nodes)


def build_document(files: dict[str, bytes], manifest: Manifest, bridge: str) -> str:
    try:
        source = files[manifest.entry].decode("utf-8")
    except UnicodeDecodeError as caught:
        raise PackageError("INTERACTIVE_HTML_ENCODING", "入口 HTML 必须是 UTF-8") from caught
    soup = BeautifulSoup(source, "html.parser")
    if soup.html is None:
        wrapper = BeautifulSoup("<html><head></head><body></body></html>", "html.parser")
        for item in list(soup.contents):
            wrapper.body.append(item.extract())
        soup = wrapper
    if soup.head is None:
        soup.html.insert(0, soup.new_tag("head"))
    for tag in list(soup.find_all(["base", "iframe", "frame", "object", "embed", "form"])):
        raise PackageError("INTERACTIVE_UNSUPPORTED_ELEMENT", f"不支持的元素：{tag.name}")
    for meta in list(soup.find_all("meta")):
        if (meta.get("http-equiv") or "").lower() in {"refresh", "content-security-policy"}:
            meta.decompose()
    base = posixpath.dirname(manifest.entry)
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        if tag.name == "script" and tag.get("type", "").lower() == "module":
            raise PackageError("INTERACTIVE_MODULE_UNSUPPORTED", "请先将 ES module 构建成普通脚本")
        if tag.name == "script" and tag.get("src"):
            tag["src"] = _asset_ref(str(tag["src"]), base=base, files=files)
        elif tag.name == "link" and tag.get("href"):
            rel = [str(value).lower() for value in tag.get("rel", [])]
            if "stylesheet" in rel:
                name = posixpath.normpath(posixpath.join(base, str(tag["href"])))
                if name not in files:
                    raise PackageError("INTERACTIVE_FILE_MISSING", "样式文件不存在")
                try:
                    css = files[name].decode("utf-8")
                except UnicodeDecodeError as caught:
                    raise PackageError("INTERACTIVE_CSS_ENCODING", "CSS 必须是 UTF-8") from caught
                replacement = soup.new_tag("style")
                replacement.string = _rewrite_css(css, base=posixpath.dirname(name), files=files)
                tag.replace_with(replacement)
                continue
            if "icon" in rel:
                tag["href"] = _asset_ref(str(tag["href"]), base=base, files=files)
            else:
                raise PackageError("INTERACTIVE_EXTERNAL_ASSET", "不支持外部链接标签")
        elif tag.name == "a" and tag.get("href") and not str(tag["href"]).startswith("#"):
            raise PackageError("INTERACTIVE_NAVIGATION", "互动内容不能跳转到其他页面")
        for attr in ("src", "poster"):
            if tag.name == "script" and attr == "src":
                continue
            if tag.get(attr):
                tag[attr] = _asset_ref(str(tag[attr]), base=base, files=files)
        if tag.get("srcset"):
            raise PackageError("INTERACTIVE_SRCSET", "请将 srcset 素材改为单个 src")
        if tag.get("style"):
            tag["style"] = _rewrite_css(str(tag["style"]), base=base, files=files)
        if tag.name == "style" and tag.string:
            tag.string = _rewrite_css(str(tag.string), base=base, files=files)
    policy = soup.new_tag("meta", attrs={"http-equiv": "Content-Security-Policy", "content": CSP})
    soup.head.insert(0, policy)
    assets = {
        name: _data_uri(name, data) for name, data in files.items() if name != "manifest.json"
    }
    asset_json = json.dumps(assets, separators=(",", ":"), ensure_ascii=True).replace(
        "<", "\\u003c"
    )
    shim = soup.new_tag("script")
    shim.string = f"window.__K12_ASSETS__={asset_json};\n{bridge}"
    soup.head.insert(1, shim)
    result = "<!doctype html>\n" + str(soup)
    if len(result.encode("utf-8")) > MAX_EXPANDED:
        raise PackageError("INTERACTIVE_DOCUMENT_TOO_LARGE", "播放文档超过上限")
    return result


def file_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
