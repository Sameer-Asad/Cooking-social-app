from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    conversation_id: UUID
    rag_enabled: bool
    chunks_indexed: int
