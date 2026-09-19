"""HTTP DTOs for the conversation/run API (T12)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

OperationId = Literal["TEACH_TURN", "CODE_FEEDBACK"]


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: uuid.UUID


class SessionSummary(BaseModel):
    id: uuid.UUID
    chapter_id: uuid.UUID
    chapter_title: str
    curriculum_revision: str
    stage: str
    grade: int | None
    base_revision: int
    created_at: datetime
    message_count: int
    last_message_at: datetime | None


class MessageDTO(BaseModel):
    id: uuid.UUID
    role: str
    content_markdown: str
    card: dict[str, Any] | None
    created_at: datetime


class SessionDetail(SessionSummary):
    messages: list[MessageDTO]


class TurnCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    idempotency_key: str = Field(min_length=1, max_length=160)
    operation: OperationId = "TEACH_TURN"


class RunDTO(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    operation: str
    status: str
    attempt: int
    fixture: bool
    error_category: str | None
    stale_reason: str | None
    card: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    idempotent_replay: bool = False


class TurnAccepted(BaseModel):
    run: RunDTO


class LessonEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: str = Field(min_length=3, max_length=24)
    message: str | None = Field(default=None, max_length=8000)
    reference: str | None = Field(default=None, max_length=160)
    idempotency_key: str | None = Field(default=None, max_length=160)


class LessonPhaseDTO(BaseModel):
    session_id: uuid.UUID
    phase: str
    lifecycle: str
    phase_revision: int
    policy: dict[str, Any]
    policy_snapshot_id: uuid.UUID | None
    evidence: dict[str, Any]
    run: RunDTO | None = None
    proactive_opening: str | None = None
