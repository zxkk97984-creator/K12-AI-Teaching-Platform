"""Versioned extraction contracts; source quotations are verified again by the service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = ("PREFERENCE", "INTEREST", "GOAL", "PLAN", "EXPERIENCE", "LEARNING")


class SourceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    session_id: str
    observed_at: str
    text: str = Field(max_length=8000)


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["k12.memory.extract.request.v1"] = "k12.memory.extract.request.v1"
    request_id: str
    sources: list[SourceMessage] = Field(max_length=20)
    existing: list[dict[str, str]] = Field(default_factory=list, max_length=200)


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=2, max_length=160)
    category: Literal["PREFERENCE", "INTEREST", "GOAL", "PLAN", "EXPERIENCE", "LEARNING"]
    statement: str = Field(min_length=2, max_length=400)
    source_message_id: str
    quote: str = Field(min_length=2, max_length=1000)
    certainty: Literal["EXPLICIT", "UNCERTAIN"]
    valid_until: str | None = None


class ExtractedSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    summary: str = Field(min_length=2, max_length=1200)
    source_message_ids: list[str] = Field(min_length=1, max_length=20)


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["k12.memory.extract.response.v1"] = "k12.memory.extract.response.v1"
    request_id: str
    facts: list[ExtractedFact] = Field(max_length=40)
    summaries: list[ExtractedSummary] = Field(default_factory=list, max_length=20)


class MemorySettingsView(BaseModel):
    auto_enabled: bool
    use_enabled: bool
    revision: int


class MemorySourceView(BaseModel):
    session_id: str
    message_id: str
    observed_at: str
    deleted: bool


class MemoryItemView(BaseModel):
    id: str
    key: str
    category: str
    statement: str
    status: str
    manual: bool
    revision: int
    sources: list[MemorySourceView]
    valid_until: datetime | None
    updated_at: datetime


class MemoryTaskView(BaseModel):
    id: str
    session_id: str
    status: str
    reason: str | None
    attempt: int
    updated_at: datetime


class MemoryOverviewView(BaseModel):
    total: int = 0
    offset: int = 0
    has_more: bool = False
    settings: MemorySettingsView
    content_revision: int
    last_updated_at: datetime | None
    items: list[MemoryItemView]
    summary_markdown: str
    tasks: list[MemoryTaskView]
    notice: str


def export_contracts() -> None:
    import json
    from pathlib import Path

    from app.modules.ai.extraction import INSTRUCTION

    root = Path(__file__).resolve().parents[4]
    asset = root / "platform/knodo/memory/v1"
    asset.mkdir(parents=True, exist_ok=True)
    (asset / "system-prompt.md").write_text("# 个人记忆整理助手\n\n" + INSTRUCTION + "\n")
    for name, model in (
        ("memory-extract-request", ExtractionRequest),
        ("memory-extract-response", ExtractionResponse),
    ):
        text = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
        for directory in (root / "contracts", root / "platform/knodo/contracts", asset):
            (directory / (name + ".schema.json")).write_text(text)


if __name__ == "__main__":
    export_contracts()
