import asyncio

from sqlalchemy import select

from app.bot.user_memory import merge_session_into_memory
from app.celery_app import celery_app
from app.core.ids import to_uuid
from app.core.pii_scan import redact, scan_for_pii
from app.db.session import AsyncSessionLocal
from app.models.models import Conversation, Message, User


@celery_app.task(name="tasks.summarize_session_into_user_md")
def summarize_session_into_user_md(conversation_id: str, user_id: str) -> None:
    """Fired by one of the three session-end triggers (Sec 4.4):
    the 20-message cap, the 30-min inactivity timeout, or the
    navigator.sendBeacon() best-effort tab-close signal."""
    asyncio.run(_run(conversation_id, user_id))


async def _run(conversation_id: str, user_id: str) -> None:
    conversation_uuid = to_uuid(conversation_id)
    user_uuid = to_uuid(user_id)

    async with AsyncSessionLocal() as db:
        messages_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_uuid)
            .order_by(Message.created_at)
        )
        messages = messages_result.scalars().all()
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)

        user_result = await db.execute(select(User).where(User.id == user_uuid))
        user = user_result.scalar_one()

        updated_memory = await merge_session_into_memory(user.memory_md, transcript)
        # Sec 11.2 — zero-tolerance PII gate, run synchronously before the
        # write to Postgres. Redact rather than block, so a false positive
        # doesn't silently drop an otherwise-useful memory update.
        if scan_for_pii(updated_memory):
            updated_memory = redact(updated_memory)
        user.memory_md = updated_memory

        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_uuid)
        )
        conversation = conv_result.scalar_one()
        conversation.is_locked = True

        await db.commit()
