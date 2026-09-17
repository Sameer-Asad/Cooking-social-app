from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limit import RateLimitExceeded, TokenBucketLimiter, enforce_all_tiers
from app.core.security import decode_token
from app.core.ids import to_uuid
from app.db.session import get_db
from app.models.models import User

_redis: Redis | None = None
_limiter: TokenBucketLimiter | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.upstash_redis_url,
            ssl_cert_reqs="none",
            health_check_interval=30,  # ping idle pooled connections, replace dead ones
            socket_keepalive=True,
            retry_on_timeout=True,
            retry_on_error=[ConnectionError, TimeoutError],
        )
    return _redis


def get_limiter(redis: Redis = Depends(get_redis)) -> TokenBucketLimiter:
    global _limiter
    if _limiter is None:
        _limiter = TokenBucketLimiter(redis)
    return _limiter


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(access_token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    result = await db.execute(select(User).where(User.id == to_uuid(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def enforce_bot_rate_limits(
    request: Request,
    user: User = Depends(get_current_user),
    limiter: TokenBucketLimiter = Depends(get_limiter),
    groq_tokens_cost: int = 0,
    tts_cost: int = 0,
) -> None:
    try:
        await enforce_all_tiers(
            limiter,
            ip=request.client.host if request.client else "unknown",
            user_id=str(user.id),
            is_paid=user.is_paid_tier,
            groq_tokens_cost=groq_tokens_cost,
            tts_cost=tts_cost,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Daily question limit reached — resets in ~{exc.retry_after_seconds}s",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
