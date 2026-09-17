import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.models import Conversation
from app.tasks.memory_tasks import summarize_session_into_user_md


@celery_app.task(name="tasks.lock_inactive_conversations")
def lock_inactive_conversations() -> None:
    """Sec 4.4 trigger #2 — DISABLED. Conversations no longer auto-lock
    from inactivity; they only lock on the 20-message cap or tab close.
    Kept as a no-op (rather than deleted) so nothing errors if the
    Celery beat schedule still references this task name."""
    return
