from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.identity.models import PreferredStyle, Stage, UserRole, VoicePreference

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


class PreferencesDTO(StrictModel):
    preferred_style: PreferredStyle
    interests: list[ShortText]
    proactive_guidance_enabled: bool
    voice_preference: VoicePreference
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

    @model_validator(mode="after")
    def require_change(self) -> ProfilePatch:
        if not ({"stage", "grade"} & self.model_fields_set):
            raise ValueError("at least one profile field is required")
        return self


class PreferencesPatch(VersionedPatch):
    preferred_style: PreferredStyle | None = None
    interests: list[ShortText] | None = Field(default=None, max_length=10)
    proactive_guidance_enabled: bool | None = None
    voice_preference: VoicePreference | None = None

    @model_validator(mode="after")
    def require_change(self) -> PreferencesPatch:
        fields = {"preferred_style", "interests", "proactive_guidance_enabled", "voice_preference"}
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
