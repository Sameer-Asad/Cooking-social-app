import asyncio

from redis import Redis as SyncRedis

from app.bot.tts import synthesize
from app.celery_app import celery_app
from app.config import settings


@celery_app.task(name="tasks.pregenerate_tts")
def pregenerate_tts(text: str, lang: str) -> None:
    """Optional warm-cache task — e.g. call this right after the bot's
    text answer is produced so the audio is already cached by the time
    the client polls for it, instead of generating on first request."""

    async def _run() -> None:
        # A plain sync redis.Redis works fine inside a Celery task (it
        # doesn't need to share the event loop with FastAPI); we still
        # await synthesize() by wrapping it with asyncio.run at the task
        # boundary since tts.synthesize is async (it awaits run_in_executor).
        redis = SyncRedis.from_url(settings.upstash_redis_url)
        from redis.asyncio import Redis as AsyncRedis

        async_redis = AsyncRedis.from_url(settings.upstash_redis_url)
        try:
            await synthesize(async_redis, text, lang)
        finally:
            await async_redis.aclose()
            redis.close()

    asyncio.run(_run())
