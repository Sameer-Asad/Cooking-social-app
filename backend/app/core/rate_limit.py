"""
Token bucket via an atomic Lua script (Sec 8.1) — not fixed-window counters.
Uses redis.asyncio's Script object (register_script), which loads the Lua
code once and calls EVALSHA thereafter, retrying with EVAL on NOSCRIPT.
Ref: redis-py Lua Scripting docs (register_script / Script object).

Implements the check order from Sec 8.2 (cheapest first):
  1. Per-IP            2. Per-user daily question count
  3. Per-user Groq tokens   4. App-wide Groq RPM guard
  5. Per-resource (TTS)
"""

from __future__ import annotations

import time

from redis.asyncio import Redis

from app.config import settings

# KEYS[1] = bucket key
# ARGV[1] = max tokens (bucket capacity)
# ARGV[2] = refill rate (tokens per second)
# ARGV[3] = cost of this request (tokens to consume)
# ARGV[4] = now (unix seconds, float)
#
# Returns {allowed (0/1), remaining_tokens, retry_after_seconds}
_TOKEN_BUCKET_LUA = """
local bucket_key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local data = redis.call("HMGET", bucket_key, "tokens", "ts")
local tokens = tonumber(data[1])
local last_ts = tonumber(data[2])

if tokens == nil then
  tokens = capacity
  last_ts = now
end

-- Refill based on elapsed time since last check.
local elapsed = math.max(0, now - last_ts)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call("HMSET", bucket_key, "tokens", tokens, "ts", now)
-- Expire the bucket well after it would naturally refill, so idle buckets
-- don't linger forever in Upstash (which bills/limits by command + storage).
redis.call("EXPIRE", bucket_key, math.ceil(capacity / refill_rate) + 60)

local retry_after = 0
if allowed == 0 then
  retry_after = math.ceil((cost - tokens) / refill_rate)
end

return {allowed, tokens, retry_after}
"""


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int, scope: str):
        self.retry_after_seconds = retry_after_seconds
        self.scope = scope
        super().__init__(
            f"Rate limit exceeded for scope={scope}, retry_after={retry_after_seconds}s"
        )


class TokenBucketLimiter:
    """One instance wraps one Redis connection; the Lua script is
    registered once and reused (EVALSHA) for every bucket key."""

    def __init__(self, redis: Redis):
        self._redis = redis
        self._script = redis.register_script(_TOKEN_BUCKET_LUA)

    async def check(
        self,
        *,
        key: str,
        capacity: int,
        refill_rate_per_sec: float,
        cost: float = 1.0,
    ) -> None:
        now = time.time()
        allowed, remaining, retry_after = await self._script(
            keys=[key],
            args=[capacity, refill_rate_per_sec, cost, now],
        )
        if not int(allowed):
            raise RateLimitExceeded(retry_after_seconds=int(retry_after), scope=key)


def _per_day_rate(count_per_day: int) -> float:
    """Convert a daily budget into a refill-rate-per-second for the bucket,
    so the bucket naturally spreads the budget across 24h rather than
    letting it all be spent in one burst at day-start."""
    return count_per_day / 86400.0


async def enforce_all_tiers(
    limiter: TokenBucketLimiter,
    *,
    ip: str,
    user_id: str,
    is_paid: bool,
    groq_tokens_cost: int = 0,
    tts_cost: int = 0,
) -> None:
    """Runs the Sec 8.2 check order, cheapest first, rejecting on the first
    tier that's exhausted (so we never do the expensive Groq-token check
    for a request that a cheap per-IP check would already reject)."""

    # Tier 1 — per-IP anti-scrape, checked before auth.
    await limiter.check(
        key=f"rl:ip:{ip}",
        capacity=settings.ip_requests_per_min,
        refill_rate_per_sec=_per_day_rate(settings.ip_requests_per_min * 60 * 24),
    )

    # Tier 2 — per-user daily question count.
    daily_q = (
        settings.paid_questions_per_day if is_paid else settings.free_questions_per_day
    )
    await limiter.check(
        key=f"rl:user:questions:{user_id}",
        capacity=daily_q,
        refill_rate_per_sec=_per_day_rate(daily_q),
    )

    # Tier 3 — per-user Groq token bucket (real cost control).
    if groq_tokens_cost:
        daily_tokens = (
            settings.paid_groq_tokens_per_day
            if is_paid
            else settings.free_groq_tokens_per_day
        )
        await limiter.check(
            key=f"rl:user:groqtokens:{user_id}",
            capacity=daily_tokens,
            refill_rate_per_sec=_per_day_rate(daily_tokens),
            cost=groq_tokens_cost,
        )

    # Tier 4 — app-wide Groq RPM guard (Sec 8.4) — protects the shared
    # organization-level 30 RPM cap Groq enforces across ALL users.
    await limiter.check(
        key="rl:app:groq_rpm",
        capacity=settings.app_wide_groq_rpm_guard,
        refill_rate_per_sec=settings.app_wide_groq_rpm_guard / 60.0,
    )

    # Tier 5 — per-resource TTS.
    if tts_cost:
        daily_tts = settings.paid_tts_per_day if is_paid else settings.free_tts_per_day
        await limiter.check(
            key=f"rl:user:tts:{user_id}",
            capacity=daily_tts,
            refill_rate_per_sec=_per_day_rate(daily_tts),
            cost=tts_cost,
        )
