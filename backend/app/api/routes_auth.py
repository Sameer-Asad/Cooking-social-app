from __future__ import annotations

import secrets

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.config import settings
from app.core.display import display_name
from app.core.ids import to_uuid
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_TTL_SECONDS = 300  # 5-min TTL, per Sec 6


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    username: str | None = Field(default=None, min_length=3, max_length=50)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SetUsernameRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str
) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_access_ttl_min * 60,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_refresh_ttl_days * 24 * 3600,
    )


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "display_name": display_name(user),
        "is_paid_tier": user.is_paid_tier,
    }


@router.post("/signup")
async def signup(
    body: SignupRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    if body.username:
        existing_username = await db.execute(
            select(User).where(User.username == body.username)
        )
        if existing_username.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        username=body.username,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access = create_access_token(str(user.id))
    refresh, _jti = create_refresh_token(str(user.id))
    _set_auth_cookies(response, access, refresh)
    return _user_dict(user)


@router.post("/login")
async def login(
    body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if (
        not user
        or not user.hashed_password
        or not verify_password(body.password, user.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access = create_access_token(str(user.id))
    refresh, _jti = create_refresh_token(str(user.id))
    _set_auth_cookies(response, access, refresh)
    return _user_dict(user)


@router.post("/refresh")
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    jti = payload.get("jti")
    if jti and await redis.get(f"jwt:blacklist:{jti}"):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    result = await db.execute(select(User).where(User.id == to_uuid(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if jti:
        await redis.set(
            f"jwt:blacklist:{jti}",
            "1",
            ex=settings.jwt_refresh_ttl_days * 24 * 3600,
        )

    access = create_access_token(str(user.id))
    new_refresh, _new_jti = create_refresh_token(str(user.id))
    _set_auth_cookies(response, access, new_refresh)
    return _user_dict(user)


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis),
):
    if refresh_token:
        payload = decode_token(refresh_token)
        if payload and payload.get("jti"):
            await redis.set(
                f"jwt:blacklist:{payload['jti']}",
                "1",
                ex=settings.jwt_refresh_ttl_days * 24 * 3600,
            )
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"ok": True}


@router.patch("/me/username")
async def set_username(
    body: SetUsernameRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lets a user set (or change) their username — in particular, for
    accounts that signed up before username existed and got NULL."""
    existing = await db.execute(select(User).where(User.username == body.username))
    other = existing.scalar_one_or_none()
    if other and other.id != user.id:
        raise HTTPException(status_code=409, detail="Username already taken")

    user.username = body.username
    await db.commit()
    return _user_dict(user)


@router.get("/github/login")
async def github_login(response: Response, redis: Redis = Depends(get_redis)):
    state = secrets.token_urlsafe(32)
    await redis.set(f"oauth:state:{state}", "1", ex=OAUTH_STATE_TTL_SECONDS)
    authorize_url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_oauth_redirect_uri}"
        f"&state={state}"
        "&scope=read:user user:email"
    )
    return {"authorize_url": authorize_url}


@router.get("/github/callback")
async def github_callback(
    code: str,
    state: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    stored = await redis.get(f"oauth:state:{state}")
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    await redis.delete(f"oauth:state:{state}")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
        )
        token_data = token_resp.json()
        provider_token = token_data.get("access_token")
        if not provider_token:
            raise HTTPException(status_code=400, detail="GitHub OAuth exchange failed")

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {provider_token}"},
        )
        github_user = user_resp.json()

    github_id = str(github_user["id"])
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            email=github_user.get("email") or f"{github_id}@users.noreply.github.com",
            github_id=github_id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access = create_access_token(str(user.id))
    refresh, _jti = create_refresh_token(str(user.id))
    _set_auth_cookies(response, access, refresh)
    return _user_dict(user)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return _user_dict(user)
