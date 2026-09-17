from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.bot.rag.chunker import chunk_text
from app.bot.rag.document_parser import ACCEPTED_CONTENT_TYPES, extract_text
from app.bot.rag.qdrant_client import index_chunks
from app.models.models import Conversation, User
from app.schemas.rag import DocumentUploadResponse

router = APIRouter(prefix="/bot", tags=["bot", "rag"])

# Sec 4.5 — plain text/markdown, PDF, and modern .docx are supported.
# Legacy .doc is explicitly rejected in document_parser.extract_text
# with a clear message, rather than silently misreading its binary
# format as UTF-8 text.
_MAX_UPLOAD_BYTES = 10_000_000  # 10MB — raised from 2MB now that PDFs/docx are in scope


@router.post(
    "/conversations/{conversation_id}/document", response_model=DocumentUploadResponse
)
async def upload_document(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sec 4.5: upload a document and opt this conversation into RAG
    context for its remaining turns. Only one document is indexed per
    user at a time (indexing a new one overwrites the prior collection
    via qdrant_client's per-user collection scoping) — this endpoint
    doesn't yet support multiple concurrent documents per user."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if file.content_type not in ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {file.content_type!r} — supported: .txt, .md, .pdf, .docx.",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File is too large (10MB limit).")

    text = extract_text(file.content_type, raw_bytes)
    if not text.strip():
        raise HTTPException(status_code=400, detail="File is empty.")

    chunks = chunk_text(text)
    index_chunks(str(user.id), chunks)

    conversation.rag_enabled = True
    await db.commit()

    return DocumentUploadResponse(
        conversation_id=conversation_id, rag_enabled=True, chunks_indexed=len(chunks)
    )


@router.delete(
    "/conversations/{conversation_id}/document", response_model=DocumentUploadResponse
)
async def disable_document_rag(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Opt back out of doc RAG for this conversation's remaining turns
    (the indexed chunks themselves aren't deleted from Qdrant here —
    they're scoped per-user and get overwritten on the next upload)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation.rag_enabled = False
    await db.commit()

    return DocumentUploadResponse(
        conversation_id=conversation_id, rag_enabled=False, chunks_indexed=0
    )
