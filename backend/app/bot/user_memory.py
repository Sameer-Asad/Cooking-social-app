"""
user.md — persistent cross-session memory (Sec 4.4). Stored as a Postgres
text column (users.memory_md), not on disk. Starts empty for a new user.

The actual summarize-and-merge step runs as a Celery background task
(tasks/memory_tasks.py) so it never blocks the request/response path.
This module holds the pure logic: reading current memory, and merging a
new session summary into it.
"""

from __future__ import annotations

from groq import AsyncGroq
from langsmith import traceable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.ids import to_uuid
from app.models.models import User

_MERGE_SYSTEM_PROMPT = """\
You maintain a running memory file about a recipe-bot user, across sessions.
You will be given the CURRENT memory file (may be empty) and a NEW session's
conversation. Produce an UPDATED memory file that:
- Preserves durable facts from the current file (dietary preferences,
  skill level, dishes they've asked about repeatedly, disliked ingredients).
- Merges in anything durable from the new session — don't just append,
  fold related facts together and drop anything that's now redundant.
- Stays concise (a few short bullet points, not a transcript).
- Never includes anything from a single throwaway question that isn't
  likely to recur.
Return ONLY the updated memory file text, nothing else.
"""


async def get_user_memory(db: AsyncSession, user_id: str) -> str:
    result = await db.execute(select(User.memory_md).where(User.id == to_uuid(user_id)))
    row = result.scalar_one_or_none()
    return row or ""


@traceable(name="summarize_session_into_user_memory")
async def merge_session_into_memory(
    current_memory_md: str, session_transcript: str
) -> str:
    """Called by the Celery memory task at session-end. A separate Groq
    call, not part of the user-facing agentic loop, so it never adds
    latency to the bot's response."""
    client = AsyncGroq(api_key=settings.groq_api_key)
    completion = await client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _MERGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"CURRENT MEMORY FILE:\n{current_memory_md or '(empty)'}\n\n"
                    f"NEW SESSION TRANSCRIPT:\n{session_transcript}"
                ),
            },
        ],
        temperature=0.2,
    )
    return completion.choices[0].message.content.strip()


async def save_user_memory(
    db: AsyncSession, user_id: str, updated_memory_md: str
) -> None:
    result = await db.execute(select(User).where(User.id == to_uuid(user_id)))
    user = result.scalar_one()
    user.memory_md = updated_memory_md
    await db.commit()
