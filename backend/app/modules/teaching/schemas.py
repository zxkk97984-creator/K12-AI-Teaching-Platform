"""HTTP DTOs for the conversation/run API (T12)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

OperationId = Literal["TEACH_TURN", "CODE_FEEDBACK"]


class SceneSnapshot(BaseModel):
    """Small, owner-scoped page snapshot captured at send time.

    The client may describe the visible learning surface, but the server still
    owns identity, content visibility and all durable relationships.
    """

    model_config = ConfigDict(extra="forbid")

    route: str = Field(default="", max_length=240)
    page_type: str = Field(default="", max_length=64)
    chapter_id: str | None = Field(default=None, max_length=80)
    chapter_title: str | None = Field(default=None, max_length=200)
    content_block_id: str | None = Field(default=None, max_length=160)
    visible_section: str | None = Field(default=None, max_length=200)
    selected_text: str | None = Field(default=None, max_length=4000)
    content_kind: Literal["PICTUREBOOK", "GUIDED_ANIMATION", "INTERACTIVE"] | None = None
    content_id: str | None = Field(default=None, max_length=80)
    content_version: str | None = Field(default=None, max_length=80)
    section_index: int | None = Field(default=None, ge=0, le=1000)
    knowledge_points: list[str] = Field(default_factory=list, max_length=12)
    activity_type: str | None = Field(default=None, max_length=64)
    task_id: str | None = Field(default=None, max_length=80)
    task_revision: int | None = Field(default=None, ge=1, le=10000)
    code_hash: str | None = Field(default=None, max_length=64)
    execution_status: str | None = Field(default=None, max_length=32)
    quiz_session_id: str | None = Field(default=None, max_length=80)
    question_id: str | None = Field(default=None, max_length=80)
    interactive_session_id: str | None = Field(default=None, max_length=80)
    interactive_scene_id: str | None = Field(default=None, max_length=100)
    interactive_prompt_id: str | None = Field(default=None, max_length=100)


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: uuid.UUID


class ConversationCreateRequest(BaseModel):
    """Create a free conversation, or a chapter-backed conversation when supplied."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    chapter_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)


class ConversationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


class SessionSummary(BaseModel):
    id: uuid.UUID
    chapter_id: uuid.UUID | None
    chapter_title: str
    conversation_type: Literal["LESSON", "FREE"] = "LESSON"
    title: str
    archived_at: datetime | None = None
    curriculum_revision: str
    stage: str
    grade: int | None
    base_revision: int
    created_at: datetime
    message_count: int
    last_message_at: datetime | None


class MessageDTO(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID | None = None
    role: str
    content_markdown: str
    card: dict[str, Any] | None
    created_at: datetime


class SessionDetail(SessionSummary):
    messages: list[MessageDTO]
    active_run_id: uuid.UUID | None = None


class TurnCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)
    idempotency_key: str = Field(min_length=1, max_length=160)
    operation: OperationId = "TEACH_TURN"
    scene: SceneSnapshot | None = None


class RunDTO(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    operation: str
    status: str
    attempt: int
    fixture: bool
    error_category: str | None
    stale_reason: str | None
    draft_markdown: str | None = None
    card: dict[str, Any] | None
    result_message_id: uuid.UUID | None = None
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
