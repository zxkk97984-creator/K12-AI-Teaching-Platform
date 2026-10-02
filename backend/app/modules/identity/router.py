from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, Settings
from app.core.database import get_session
from app.modules.identity.avatar import (
    INPUT_FORMATS,
    MAX_AVATAR_UPLOAD_BYTES,
    AvatarInvalid,
    get_avatar,
    normalize_avatar,
    remove_avatar,
    save_avatar,
)
from app.modules.identity.dependencies import (
    SessionContext,
    csrf_dependency,
    get_session_context,
    require_admin,
    require_student,
)
from app.modules.identity.models import UserRole
from app.modules.identity.schemas import (
    AdminStatus,
    AuthResponse,
    CsrfResponse,
    LoginRequest,
    MeResponse,
    PreferencesDTO,
    PreferencesPatch,
    ProfileDTO,
    ProfilePatch,
    UserDTO,
)
from app.modules.identity.security import new_csrf_token
from app.modules.identity.service import (
    IdentityError,
    LoginRateLimited,
    ProfileNotReady,
    RevisionConflict,
    active_session_count,
    active_student_count,
    authenticate,
    create_auth_session,
    get_profile,
    is_login_rate_limited,
    revoke_auth_session,
    update_preferences,
    update_profile,
)

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME, path="/", secure=settings.cookie_secure, samesite="lax"
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME, path="/", secure=settings.cookie_secure, samesite="lax"
    )


def _me_from_profile(user, profile) -> MeResponse:
    profile_dto = None
    preferences_dto = None
    if profile is not None:
        profile_dto = ProfileDTO(
            stage=profile.stage,
            grade=profile.grade,
            revision=profile.revision,
            onboarding_completed=profile.stage is not None,
            nickname=profile.nickname,
            avatar_url=(
                f"/api/v1/me/avatar?v={profile.avatar_sha256}"
                if profile.avatar_sha256 is not None
                else None
            ),
        )
        preferences_dto = PreferencesDTO(
            preferred_style=profile.preferred_style,
            teacher_style=profile.teacher_style,
            companion_pet_id=profile.companion_pet_id,
            interests=profile.interests,
            proactive_guidance_enabled=profile.proactive_guidance_enabled,
            voice_preference=profile.voice_preference,
            auto_read_replies=profile.auto_read_replies,
            profile_revision=profile.revision,
        )
    return MeResponse(
        user=UserDTO(id=user.id, username=user.username, role=user.role, is_active=user.is_active),
        profile=profile_dto,
        preferences=preferences_dto,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/auth/csrf", response_model=CsrfResponse)
async def csrf_token(request: Request, response: Response) -> CsrfResponse:
    settings = _settings(request)
    token = new_csrf_token()
    _set_csrf_cookie(response, token, settings)
    _no_store(response)
    return CsrfResponse(csrf_token=token)


@router.post("/auth/login", response_model=AuthResponse, dependencies=[Depends(csrf_dependency)])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> AuthResponse:
    settings = _settings(request)
    if await is_login_rate_limited(db, settings, payload.username):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁")
    try:
        user = await authenticate(db, settings, payload.username, payload.password)
    except LoginRateLimited:
        raise HTTPException(status_code=429, detail="登录尝试过于频繁") from None
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误，或账户暂不可用")
    raw_token = await create_auth_session(db, settings, user)
    profile = await get_profile(db, user.id) if user.role == UserRole.STUDENT.value else None
    me = _me_from_profile(user, profile)
    csrf = new_csrf_token()
    _set_session_cookie(response, raw_token, settings)
    _set_csrf_cookie(response, csrf, settings)
    _no_store(response)
    return AuthResponse(csrf_token=csrf, **me.model_dump())


@router.post(
    "/auth/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(csrf_dependency)]
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> Response:
    await revoke_auth_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    _clear_auth_cookies(response, _settings(request))
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
async def me(
    context: SessionContext = Depends(get_session_context),
    db: AsyncSession = Depends(get_session),
) -> MeResponse:
    profile = await get_profile(db, context.user.id)
    return _me_from_profile(context.user, profile)


@router.patch("/me/profile", response_model=MeResponse, dependencies=[Depends(csrf_dependency)])
async def patch_profile(
    patch: ProfilePatch,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> MeResponse:
    if context.user.role != UserRole.STUDENT.value:
        raise HTTPException(status_code=403, detail="仅学生可修改学习档案")
    try:
        profile = await update_profile(db, context.user.id, patch)
    except RevisionConflict as exc:
        raise HTTPException(status_code=409, detail="档案版本冲突") from exc
    except ProfileNotReady as exc:
        raise HTTPException(status_code=409, detail="学习档案尚未建立") from exc
    except IdentityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _me_from_profile(context.user, profile)


@router.get(
    "/me/avatar",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "当前账号的头像"}},
)
async def read_my_avatar(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> Response:
    avatar = await get_avatar(db, owner_user_id=context.user.id)
    if avatar is None:
        raise HTTPException(status_code=404, detail="尚未设置头像")
    return Response(
        content=avatar.image_png,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.put(
    "/me/avatar",
    response_model=MeResponse,
    dependencies=[Depends(csrf_dependency)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in INPUT_FORMATS
            },
        }
    },
)
async def upload_my_avatar(
    request: Request,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> MeResponse:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].lower().strip()
    if media_type not in INPUT_FORMATS:
        raise HTTPException(status_code=415, detail="仅支持 PNG、JPG 或 WebP 图片")
    size = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_AVATAR_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="头像文件不能超过 2 MB")
        chunks.append(chunk)
    try:
        image_png, sha256 = await asyncio.to_thread(normalize_avatar, b"".join(chunks), media_type)
    except AvatarInvalid as caught:
        raise HTTPException(status_code=422, detail=str(caught)) from caught
    try:
        profile = await save_avatar(
            db, owner_user_id=context.user.id, image_png=image_png, sha256=sha256
        )
    except ProfileNotReady as caught:
        raise HTTPException(status_code=409, detail="学习档案尚未建立") from caught
    return _me_from_profile(context.user, profile)


@router.delete("/me/avatar", response_model=MeResponse, dependencies=[Depends(csrf_dependency)])
async def delete_my_avatar(
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> MeResponse:
    try:
        profile = await remove_avatar(db, owner_user_id=context.user.id)
    except ProfileNotReady as caught:
        raise HTTPException(status_code=409, detail="学习档案尚未建立") from caught
    return _me_from_profile(context.user, profile)


@router.patch("/me/preferences", response_model=MeResponse, dependencies=[Depends(csrf_dependency)])
async def patch_preferences(
    patch: PreferencesPatch,
    context: SessionContext = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> MeResponse:
    try:
        profile = await update_preferences(db, context.user.id, patch)
    except RevisionConflict as exc:
        raise HTTPException(status_code=409, detail="档案版本冲突") from exc
    except ProfileNotReady as exc:
        raise HTTPException(status_code=409, detail="学习档案尚未建立") from exc
    return _me_from_profile(context.user, profile)


@router.get("/admin/identity/status", response_model=AdminStatus)
async def admin_status(
    context: SessionContext = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
) -> AdminStatus:
    return AdminStatus(
        role=UserRole.ADMIN,
        active_students=await active_student_count(db),
        active_sessions=await active_session_count(db),
        capabilities={"identity_admin": True, "knodo_configured": False},
    )
