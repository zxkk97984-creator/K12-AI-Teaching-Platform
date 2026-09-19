from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, Settings
from app.core.database import get_session
from app.modules.identity.models import AuthSession, User, UserRole
from app.modules.identity.security import constant_time_equal, hash_session_token


@dataclass(frozen=True)
class SessionContext:
    user: User
    auth_session: AuthSession


async def get_session_context(
    request: Request,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
    db: AsyncSession = Depends(get_session),
) -> SessionContext:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")
    from datetime import datetime

    result = await db.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == hash_session_token(session_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")
    user, auth_session = row
    auth_session.last_seen_at = datetime.now(UTC)
    return SessionContext(user=user, auth_session=auth_session)


async def require_student(
    context: SessionContext = Depends(get_session_context),
) -> SessionContext:
    if context.user.role != UserRole.STUDENT.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅学生可使用此接口")
    return context


async def require_admin(
    context: SessionContext = Depends(get_session_context),
) -> SessionContext:
    if context.user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可使用此接口")
    return context


def _csrf_failure(request: Request, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def assert_csrf(
    request: Request,
    settings: Settings,
    origin: str | None,
    csrf_header: str | None,
    csrf_cookie: str | None,
) -> None:
    # Missing Origin is rejected. We do not trust Referer or X-Forwarded-*.
    if not origin or origin not in settings.origins:
        raise _csrf_failure(request, "CSRF_ORIGIN_FAILED")
    if not constant_time_equal(csrf_header, csrf_cookie):
        raise _csrf_failure(request, "CSRF_TOKEN_INVALID")


async def csrf_dependency(
    request: Request,
    origin: Annotated[str | None, Header(alias="Origin")] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE_NAME)] = None,
) -> None:
    assert_csrf(request, request.app.state.settings, origin, csrf_header, csrf_cookie)
