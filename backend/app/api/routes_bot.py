from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis, get_limiter
from app.bot.graph import run_turn_stream, _create_completion
from app.bot.history_summarizer import (
    frozen_blocks,
    is_session_locked,
    newly_frozen_block,
)
from app.bot.injection_guard import check_for_injection
from app.bot.language_detect import detect_text_language, is_ambiguous
from app.bot.stt import requires_mandatory_edit_step, transcribe
from app.bot.tts import TTSUnavailable, synthesize
from app.bot.user_memory import get_user_memory
from app.config import settings
from app.core.rate_limit import RateLimitExceeded, TokenBucketLimiter, enforce_all_tiers
from app.models.models import Conversation, Message, User
from app.schemas.bot import ConversationOut, MessageOut
from app.tasks.memory_tasks import summarize_session_into_user_md

router = APIRouter(prefix="/bot", tags=["bot"])

_block_summary_cache: dict[str, dict[int, str]] = {}


def _sse(event: str, data: dict) -> bytes:
    """Formats one Server-Sent Events frame. Two newlines terminate a
    frame per the SSE spec — the frontend's manual parser (client.ts)
    splits on that same double-newline."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


@router.post("/conversations")
async def create_conversation(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return {"id": str(conversation.id)}


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    """A user's own sessions — create / revisit / delete."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.last_message_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # No DB-level ON DELETE CASCADE is defined on messages.conversation_id
    # (see the initial migration), so child rows must be deleted
    # explicitly before the parent row, in the same transaction.
    await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await db.commit()

    _block_summary_cache.pop(str(conversation_id), None)
    return {"ok": True}


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[MessageOut]
)
async def list_messages(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def _summarize_new_block_if_any(
    conversation_id: uuid.UUID,
    messages_before: list[Message],
    messages_after: list[Message],
) -> None:
    """When a block just froze (Sec 4.3), generate its one-time summary
    via Groq — routed through the shared `_create_completion` in
    graph.py so this gets the same Groq quota/rate-limit -> Cohere
    fallback as run_turn/run_turn_stream, instead of talking to Groq
    directly with no fallback — and cache it. Blocks are never
    re-summarized once frozen."""
    block = newly_frozen_block(len(messages_before), len(messages_after))
    if block is None:
        return

    s0, s1 = block.summarized_range
    to_summarize = messages_after[s0 - 1 : s1]
    transcript = "\n".join(f"{m.role}: {m.content}" for m in to_summarize)

    completion = await _create_completion(
        messages=[
            {
                "role": "system",
                "content": "Summarize this part of a cooking conversation in 2-3 sentences, keeping any decisions or preferences the user stated.",
            },
            {"role": "user", "content": transcript},
        ],
        tools=None,
        temperature=0.2,
    )
    summary = completion.choices[0].message.content.strip()

    cache = _block_summary_cache.setdefault(str(conversation_id), {})
    cache[block.index] = summary


@router.post("/conversations/{conversation_id}/messages")
async def ask_question(
    conversation_id: uuid.UUID,
    text: str | None = Form(default=None),
    language_hint: str | None = Form(default=None),
    audio: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    limiter: TokenBucketLimiter = Depends(get_limiter),
    user: User = Depends(get_current_user),
):
    """Streams the answer via Server-Sent Events instead of returning one
    JSON blob. Event sequence:
      meta   - sent first: conversation_id, detected_language,
               language_confidence, needs_review, question_text (the
               resolved question — typed text, or the Whisper transcript
               for a voice question, known only once transcription runs)
      status - a tool call is about to run (e.g. {"tool": "web_search"})
      token  - one chunk of the answer's text, in order
      done   - the answer finished: message_id, audio_url, audio_degraded
      error  - something failed mid-stream

    All pre-flight checks (conversation ownership/lock, rate limiting,
    audio transcription, the mandatory-edit-step gate for ur/hi) happen
    BEFORE the StreamingResponse is constructed, so they still raise a
    normal HTTPException with a normal status code — only the actual
    answer generation + TTS step happens inside the streamed generator.
    """
    if not text and not audio:
        raise HTTPException(
            status_code=400, detail="Provide a text question or a voice recording."
        )

    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.is_locked:
        raise HTTPException(
            status_code=409,
            detail="This conversation reached its message limit — start a new one.",
        )

    try:
        await enforce_all_tiers(
            limiter, ip="unknown", user_id=str(user.id), is_paid=user.is_paid_tier
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Daily question limit reached — resets in ~{exc.retry_after_seconds}s",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    detected_language = "en"
    language_confidence = 1.0
    question_text = text or ""

    if audio is not None:
        suffix = os.path.splitext(audio.filename or "")[1] or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await audio.read())
            tmp_path = tmp.name
        try:
            result = await transcribe(tmp_path, language_hint=language_hint)
        finally:
            os.unlink(tmp_path)

        detected_language = result.detected_language
        language_confidence = result.language_confidence
        question_text = result.text

        if requires_mandatory_edit_step(detected_language) and text is None:
            # Nothing was actually asked yet — this is just the raw
            # transcript going back for the user to review/edit before
            # it's really sent (Sec 3.1). One frame, then done.
            async def needs_review_stream() -> AsyncGenerator[bytes, None]:
                yield _sse(
                    "meta",
                    {
                        "conversation_id": str(conversation_id),
                        "detected_language": detected_language,
                        "language_confidence": language_confidence,
                        "needs_review": True,
                        "question_text": question_text,
                    },
                )
                yield _sse(
                    "done",
                    {"message_id": None, "audio_url": None, "audio_degraded": False},
                )

            return StreamingResponse(
                needs_review_stream(), media_type="text/event-stream"
            )
    elif text:
        detected_language, language_confidence = detect_text_language(text)

    check_for_injection(question_text)

    if is_ambiguous(language_confidence):
        pass  # the system prompt itself instructs the LLM to ask when unsure

    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=question_text,
        detected_language=detected_language,
    )
    db.add(user_msg)
    await db.commit()

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    all_messages_before_reply = list(history_result.scalars().all())

    user_memory_md = await get_user_memory(db, str(user.id))
    block_summaries = _block_summary_cache.get(str(conversation_id), {})

    raw_dicts = [
        {"role": m.role, "content": m.content} for m in all_messages_before_reply
    ]

    from app.bot.context_builder import assemble_messages

    rag_context = None
    if conversation.rag_enabled:
        from app.bot.rag.qdrant_client import hybrid_search, summarize_chunks

        retrieved_chunks = hybrid_search(str(user.id), question_text)
        if retrieved_chunks:
            rag_context = await summarize_chunks(retrieved_chunks, question_text)

    context_messages = assemble_messages(
        user_memory_md=user_memory_md,
        raw_messages=raw_dicts[:-1],
        block_summaries=block_summaries,
        rag_context=rag_context,
        current_user_message=question_text,
    )

    async def event_stream() -> AsyncGenerator[bytes, None]:
        yield _sse(
            "meta",
            {
                "conversation_id": str(conversation_id),
                "detected_language": detected_language,
                "language_confidence": language_confidence,
                "needs_review": False,
                "question_text": question_text,
            },
        )

        full_text_parts: list[str] = []
        try:
            async for event in run_turn_stream(context_messages):
                if event["type"] == "token":
                    full_text_parts.append(event["text"])
                    yield _sse("token", {"text": event["text"]})
                elif event["type"] == "status":
                    yield _sse("status", {"tool": event["tool"]})
                elif event["type"] == "final":
                    # Tokens were already streamed as they arrived above;
                    # "final" just marks completion — nothing further to
                    # emit here unless no tokens streamed at all (e.g. an
                    # empty completion), which full_text_parts already
                    # reflects correctly either way.
                    pass
        except Exception:
            yield _sse("error", {"message": "Something went wrong generating a reply."})
            return

        reply_text = "".join(full_text_parts)

        assistant_msg = Message(
            conversation_id=conversation_id, role="assistant", content=reply_text
        )
        db.add(assistant_msg)
        conversation.last_message_at = datetime.now(timezone.utc)

        total_after = len(all_messages_before_reply) + 1
        if is_session_locked(total_after):
            conversation.is_locked = True
        await db.commit()
        await db.refresh(assistant_msg)

        await _summarize_new_block_if_any(
            conversation_id,
            all_messages_before_reply,
            all_messages_before_reply + [assistant_msg],
        )

        if conversation.is_locked:
            summarize_session_into_user_md.delay(str(conversation_id), str(user.id))

        audio_url: str | None = None
        audio_degraded = False
        try:
            audio_bytes = await synthesize(redis, reply_text, detected_language)
            audio_dir = os.path.join(settings.media_root, "audio")
            os.makedirs(audio_dir, exist_ok=True)
            audio_path = os.path.join(audio_dir, f"{assistant_msg.id}.mp3")
            with open(audio_path, "wb") as f:
                f.write(audio_bytes)
            audio_url = f"/media/audio/{assistant_msg.id}.mp3"
            assistant_msg.audio_url = audio_url
            await db.commit()
        except TTSUnavailable:
            audio_degraded = True

        yield _sse(
            "done",
            {
                "message_id": str(assistant_msg.id),
                "audio_url": audio_url,
                "audio_degraded": audio_degraded,
            },
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/conversations/{conversation_id}/end-session")
async def end_session(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sec 4.4 trigger #3: best-effort tab-close signal via
    navigator.sendBeacon(). Locks the conversation and fires the same
    summarize-into-user.md task as the other two triggers."""
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not conversation.is_locked:
        conversation.is_locked = True
        await db.commit()
        summarize_session_into_user_md.delay(str(conversation_id), str(user.id))

    return {"ok": True}
