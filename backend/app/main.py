from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.integrations.knodo.gateway import build_gateway
from app.integrations.knodo.router import router as ai_gateway_router
from app.jobs.authoring_worker import recover_authoring_jobs
from app.jobs.teaching_worker import recover_runs
from app.modules.assessment.quiz_router import router as quiz_router
from app.modules.assessment.router import router as assessment_router
from app.modules.authoring.router import router as authoring_router
from app.modules.codelab.router import router as codelab_router
from app.modules.content.router import router as content_router
from app.modules.identity.middleware import SameOriginCsrfMiddleware
from app.modules.identity.router import router as identity_router
from app.modules.learning.growth_router import router as growth_router
from app.modules.memory.router import router as memory_router
from app.modules.privacy.router import router as privacy_router
from app.modules.recommendation.router import router as recommendation_router
from app.modules.resources.animation_router import router as animation_router
from app.modules.resources.router import admin_router as resources_admin_router
from app.modules.resources.router import router as resources_router
from app.modules.teaching.router import router as teaching_router


def _make_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        await recover_runs(settings)
        await recover_authoring_jobs(settings)
        try:
            yield
        finally:
            await application.state.gateway.aclose()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or get_settings()
    application = FastAPI(
        title=runtime.app_name,
        version=runtime.app_version,
        docs_url="/docs" if runtime.app_env != "production" else None,
        redoc_url=None,
        lifespan=_make_lifespan(runtime),
    )
    application.state.settings = runtime
    application.state.gateway = build_gateway(runtime)
    application.add_middleware(SameOriginCsrfMiddleware)
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )
    install_error_handlers(application)
    application.include_router(health_router)
    application.include_router(identity_router, prefix="/api/v1")
    application.include_router(content_router, prefix="/api/v1")
    application.include_router(codelab_router, prefix="/api/v1")
    application.include_router(ai_gateway_router, prefix="/api/v1")
    application.include_router(teaching_router, prefix="/api/v1")
    application.include_router(assessment_router, prefix="/api/v1")
    application.include_router(quiz_router, prefix="/api/v1")
    application.include_router(growth_router, prefix="/api/v1")
    application.include_router(memory_router, prefix="/api/v1")
    application.include_router(recommendation_router, prefix="/api/v1")
    application.include_router(resources_router, prefix="/api/v1")
    application.include_router(animation_router, prefix="/api/v1")
    application.include_router(authoring_router, prefix="/api/v1")
    application.include_router(privacy_router, prefix="/api/v1")
    application.include_router(resources_admin_router, prefix="/api/v1")
    return application


app = create_app()
