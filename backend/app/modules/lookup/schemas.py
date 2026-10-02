from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Tool = Literal["COURSE_SEARCH", "WRONG_QUESTIONS", "LEARNING_PROGRESS"]
Kind = Literal["COURSE", "RESOURCE", "WRONG_QUESTION", "PROGRESS"]
Status = Literal["OK", "EMPTY", "FAILED", "UNAVAILABLE"]
ContentType = Literal["COURSE", "RESOURCE", "READING", "LESSON", "WATCHING", "QUIZ", "CODE"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LookupInput(StrictModel):
    keyword: str = Field(default="", max_length=120)
    topic: str = Field(default="", max_length=80)
    content_type: ContentType | None = None
    since: str | None = Field(default=None, max_length=10)
    until: str | None = Field(default=None, max_length=10)
    limit: int = Field(default=5, ge=1, le=10, strict=True)

    @model_validator(mode="after")
    def valid_dates(self):
        for value in (self.since, self.until):
            if value is not None and value not in ("今天", "昨天"):
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("date must be YYYY-MM-DD, 今天 or 昨天")
        return self


class LookupQuery(StrictModel):
    tool: Tool
    parameters: LookupInput = Field(default_factory=LookupInput)

    @model_validator(mode="after")
    def supported_filters(self):
        allowed = {
            "COURSE_SEARCH": {None, "COURSE", "RESOURCE"},
            "WRONG_QUESTIONS": {None, "QUIZ"},
            "LEARNING_PROGRESS": {None, "READING", "LESSON", "WATCHING", "QUIZ", "CODE"},
        }
        if self.parameters.content_type not in allowed[self.tool]:
            raise ValueError("content type is unavailable for this query")
        if self.tool == "COURSE_SEARCH" and (self.parameters.since or self.parameters.until):
            raise ValueError("course search does not accept activity dates")
        return self


class CourseSearchInput(LookupInput):
    content_type: Literal["COURSE", "RESOURCE"] | None = None
    since: None = None
    until: None = None


class WrongQuestionsInput(LookupInput):
    content_type: Literal["QUIZ"] | None = None


class LearningProgressInput(LookupInput):
    content_type: Literal["READING", "LESSON", "WATCHING", "QUIZ", "CODE"] | None = None


class LookupPlan(StrictModel):
    schema_version: Literal["k12.teaching.turn.v1"]
    kind: Literal["lookup_request"]
    request_id: str = Field(min_length=1, max_length=160)
    lesson_session_id: str = Field(min_length=1, max_length=160)
    base_revision: int = Field(ge=0, strict=True)
    queries: list[LookupQuery] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def one_per_tool(self):
        if len({query.tool for query in self.queries}) != len(self.queries):
            raise ValueError("each tool may run only once")
        return self


class SourceRef(StrictModel):
    source_id: str = Field(min_length=1, max_length=160)
    revision: str = Field(min_length=1, max_length=160)
    locator: str = Field(min_length=1, max_length=300)


class LookupTarget(StrictModel):
    type: Literal["CHAPTER", "RESOURCE", "ANIMATION", "PICTUREBOOK", "QUIZ", "LESSON", "CODE_RUN"]
    id: str = Field(min_length=1, max_length=160)
    revision: str | None = Field(default=None, max_length=160)


class LookupCard(StrictModel):
    id: str = Field(min_length=1, max_length=160)
    tool: Tool
    kind: Kind
    status: Status
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(max_length=1200)
    queried_at: str = Field(max_length=40)
    target: LookupTarget | None = None
    route: str | None = Field(default=None, max_length=400)
    source_ref: SourceRef | None = None
    recorded_at: str | None = Field(default=None, max_length=40)
    explanation: str | None = Field(default=None, max_length=600)
    content_notice: str | None = Field(default=None, max_length=200)


class LookupResult(StrictModel):
    tool: Tool
    status: Status
    queried_at: str = Field(max_length=40)
    summary: str = Field(max_length=400)
    cards: list[LookupCard] = Field(default_factory=list, max_length=10)
    total: int | None = Field(default=None, ge=0)
    truncated: bool = False


class LookupTargetDTO(StrictModel):
    route: str
