from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BotQuestionResponse(BaseModel):
    """Superseded by the SSE event stream (see BotStreamMeta/BotStreamDone
    below) for POST /bot/conversations/{id}/messages, which now returns
    text/event-stream instead of one JSON body. Left in place in case any
    other caller still wants the old single-response shape."""

    conversation_id: UUID
    detected_language: str
    language_confidence: float
    text: str
    audio_url: str | None
    audio_degraded: bool
    needs_review: bool = False


class BotStreamMeta(BaseModel):
    """First SSE frame (event: meta), sent before any answer text.
    `question_text` is the resolved question — the typed text, or the
    Whisper transcript for a voice question (only known once
    transcription finishes, which is why it isn't in the request)."""

    conversation_id: UUID
    detected_language: str
    language_confidence: float
    needs_review: bool
    question_text: str


class BotStreamStatus(BaseModel):
    """event: status — a tool call is about to run."""

    tool: str


class BotStreamToken(BaseModel):
    """event: token — one chunk of the answer's text, in order."""

    text: str


class BotStreamDone(BaseModel):
    """Final SSE frame (event: done). `message_id` is None for the
    needs_review short-circuit, since no assistant message is ever
    created in that case."""

    message_id: UUID | None
    audio_url: str | None
    audio_degraded: bool


class BotStreamError(BaseModel):
    """event: error — something failed mid-stream."""

    message: str


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    detected_language: str | None
    audio_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    """One entry in a user's session list — create/revisit/delete."""

    id: UUID
    created_at: datetime
    last_message_at: datetime
    is_locked: bool
    rag_enabled: bool

    class Config:
        from_attributes = True
