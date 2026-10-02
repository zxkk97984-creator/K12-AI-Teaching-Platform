from __future__ import annotations

import unicodedata
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from app.modules.identity.models import (
    PreferredStyle,
    Stage,
    TeacherStyle,
    UserRole,
    VoicePreference,
)

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LoginRequest(StrictModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class CsrfResponse(StrictModel):
    csrf_token: str


class UserDTO(StrictModel):
    id: UUID
    username: str
    role: UserRole
    is_active: bool


class ProfileDTO(StrictModel):
    stage: Stage | None
    grade: int | None
    revision: int
    onboarding_completed: bool
    nickname: str | None = None
    avatar_url: str | None = None


class PreferencesDTO(StrictModel):
    preferred_style: PreferredStyle
    teacher_style: TeacherStyle
    companion_pet_id: str
    interests: list[ShortText]
    proactive_guidance_enabled: bool
    voice_preference: VoicePreference
    auto_read_replies: bool = False
    profile_revision: int


class MeResponse(StrictModel):
    user: UserDTO
    profile: ProfileDTO | None
    preferences: PreferencesDTO | None


class AuthResponse(MeResponse):
    csrf_token: str


class VersionedPatch(StrictModel):
    base_revision: int = Field(ge=0)


class ProfilePatch(VersionedPatch):
    stage: Stage | None = None
    grade: int | None = Field(default=None, ge=1, le=12, strict=True)
    nickname: str | None = Field(default=None, max_length=40)

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = unicodedata.normalize("NFC", " ".join(value.split()))
        if not normalized:
            return None
        if len(normalized) > 24 or any(
            unicodedata.category(char).startswith("C") for char in normalized
        ):
            raise ValueError("昵称需为 1–24 个可显示字符")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> ProfilePatch:
        if not ({"stage", "grade", "nickname"} & self.model_fields_set):
            raise ValueError("at least one profile field is required")
        return self


class PreferencesPatch(VersionedPatch):
    preferred_style: PreferredStyle | None = None
    teacher_style: TeacherStyle | None = None
    companion_pet_id: (
        Annotated[
            str,
            StringConstraints(
                pattern=r"^(shuangling|anya|doraemon|kun-like|lulu-capybara|shinchan)$"
            ),
        ]
        | None
    ) = None
    interests: list[ShortText] | None = Field(default=None, max_length=10)
    proactive_guidance_enabled: bool | None = None
    voice_preference: VoicePreference | None = None
    # Omission is internal; explicit null is rejected by require_change.
    auto_read_replies: StrictBool | SkipJsonSchema[None] = Field(
        default=None, json_schema_extra=lambda schema: schema.pop("default", None)
    )

    @model_validator(mode="after")
    def require_change(self) -> PreferencesPatch:
        fields = {
            "preferred_style",
            "teacher_style",
            "companion_pet_id",
            "interests",
            "proactive_guidance_enabled",
            "voice_preference",
            "auto_read_replies",
        }
        if not (fields & self.model_fields_set):
            raise ValueError("at least one preference field is required")
        if any(getattr(self, field) is None for field in fields & self.model_fields_set):
            raise ValueError("preference fields cannot be null")
        return self


class AdminStatus(StrictModel):
    role: UserRole
    active_students: int
    active_sessions: int
    capabilities: dict[str, Any]
