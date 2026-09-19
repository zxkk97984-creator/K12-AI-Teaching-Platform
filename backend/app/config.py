from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SESSION_COOKIE_NAME = "sl_session"
CSRF_COOKIE_NAME = "sl_csrf"


class Settings(BaseSettings):
    """Runtime settings loaded only from the process environment.

    No dotenv file is read. Deployment must inject values through its secret
    manager so an old project's .env cannot silently become authoritative.
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_name: str = "霜铃 K12 本地业务服务"
    app_version: str = "0.2.0"
    app_env: Literal["development", "test", "production"] = "development"
    app_session_secret: str | None = None
    database_url: str | None = None
    test_database_url: str | None = None
    allowed_origins: str = Field(default="http://127.0.0.1:15173")
    cookie_secure: bool = False
    session_ttl_seconds: int = Field(default=8 * 60 * 60, ge=300, le=30 * 24 * 60 * 60)
    login_rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=300, ge=10, le=3600)
    argon2_time_cost: int = Field(default=3, ge=1, le=10)
    argon2_memory_cost_kib: int = Field(default=65536, ge=8192, le=1048576)
    argon2_parallelism: int = Field(default=1, ge=1, le=4)
    gateway_mode: Literal["disabled", "fixture", "knodo"] = "disabled"
    knodo_base_url: str | None = None
    knodo_token_env_var: str = Field(default="KNODO_PAT", min_length=1, max_length=64)
    gateway_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    gateway_max_output_bytes: int = Field(default=262144, ge=1024, le=4194304)
    teaching_autorun: bool = True  # API schedules the in-process worker per run
    teaching_fixture_delay_seconds: float = Field(default=0.0, ge=0.0, le=10.0)
    teaching_lease_seconds: int = Field(default=60, ge=10, le=600)
    teaching_sse_poll_seconds: float = Field(default=0.25, ge=0.02, le=2.0)
    teaching_sse_heartbeat_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    quiz_max_attempts_per_question: int = Field(default=2, ge=1, le=5)
    quiz_max_hints_per_question: int = Field(default=3, ge=1, le=3)
    # T18: conservative bounds for evidence projection and context injection.
    growth_projection_max_events: int = Field(default=200, ge=10, le=2000)
    growth_context_evidence_limit: int = Field(default=6, ge=0, le=8)
    growth_context_memory_limit: int = Field(default=4, ge=0, le=6)
    # T19: conservative bounds for the single next-step decision.
    recommendation_evidence_limit: int = Field(default=100, ge=10, le=500)
    recommendation_memory_limit: int = Field(default=4, ge=0, le=6)
    # T20: restricted local storage for registered learning resources.
    resource_storage_root: str = Field(default="storage/resources", min_length=1, max_length=400)
    resource_upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=200 * 1024 * 1024)
    resource_ticket_ttl_seconds: int = Field(default=120, ge=15, le=900)
    # T22: authoring (教研) generation budget and artefact roots.
    authoring_max_attempts: int = Field(default=2, ge=1, le=5)
    authoring_lease_seconds: int = Field(default=120, ge=10, le=3600)
    authoring_fixture_delay_seconds: float = Field(default=0.0, ge=0.0, le=10.0)
    authoring_artifact_root: str = Field(default="storage/authoring", min_length=1, max_length=400)
    authoring_bundle_root: str = Field(
        default="platform/knodo/bundles/authoring", min_length=1, max_length=400
    )
    # T26 local bridge: FastAPI never owns Docker; a loopback runner process does.
    codelab_runner_url: str | None = None
    codelab_runner_token: str | None = None

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        if not self.app_session_secret or len(self.app_session_secret) < 32:
            raise ValueError("APP_SESSION_SECRET must contain at least 32 characters")
        if not self.origins:
            raise ValueError("ALLOWED_ORIGINS must contain at least one origin")
        if self.app_env == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if any(not origin.startswith("https://") for origin in self.origins):
                raise ValueError("production ALLOWED_ORIGINS must use https")
        if self.gateway_mode == "fixture" and self.app_env == "production":
            raise ValueError("GATEWAY_MODE=fixture is forbidden in production")
        if self.gateway_mode == "knodo":
            if not self.knodo_base_url:
                raise ValueError("KNODO_BASE_URL is required when GATEWAY_MODE=knodo")
            if not self.knodo_base_url.startswith(("http://", "https://")):
                raise ValueError("KNODO_BASE_URL must be an absolute http(s) URL")
            if self.app_env == "production" and not self.knodo_base_url.startswith("https://"):
                raise ValueError("production KNODO_BASE_URL must use https")
            if not os.environ.get(self.knodo_token_env_var):
                raise ValueError(f"{self.knodo_token_env_var} must be set when GATEWAY_MODE=knodo")
        return self

    @property
    def active_database_url(self) -> str:
        if self.app_env == "test":
            if not self.test_database_url:
                raise RuntimeError("TEST_DATABASE_URL is required when APP_ENV=test")
            return self.test_database_url
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is required")
        return self.database_url

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
