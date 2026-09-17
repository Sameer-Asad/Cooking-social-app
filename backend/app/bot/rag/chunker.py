"""Semantic chunker for the optional doc-RAG path (Sec 4.5).

Splits text into sentences, embeds each one, and groups consecutive
sentences into a chunk as long as they stay topically similar (cosine
similarity above `similarity_threshold`) — starting a new chunk when the
topic shifts, or when the running chunk hits `chunk_size` regardless of
similarity, so one very-similar passage can't grow unboundedly large.

Reuses qdrant_client's dense embedding model rather than loading a
second SentenceTransformer instance.
"""

from __future__ import annotations

import re

import numpy as np

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    sentences = _SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,  # kept for call-site compatibility; unused in the
    # semantic path — semantic grouping replaces
    # fixed-offset overlap with topic-based boundaries
    similarity_threshold: float = 0.55,
) -> list[str]:
    """Groups sentences into semantically coherent chunks. `chunk_size` is
    a hard character cap per chunk (a topic can't grow a chunk past this
    even if similarity stays high) — same parameter name/position as the
    old fixed-size version so existing call sites don't need to change."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    sentences = _split_sentences(text)
    if not sentences:
        return []
    if len(sentences) == 1:
        return sentences

    from app.bot.rag.qdrant_client import (
        get_dense_model,
    )  # lazy import — avoids a hard dependency for callers that don't touch RAG

    model = get_dense_model()
    embeddings = model.encode(sentences)

    chunks: list[str] = []
    current_sentences = [sentences[0]]
    current_len = len(sentences[0])

    for i in range(1, len(sentences)):
        sentence = sentences[i]
        sim = _cosine_sim(embeddings[i - 1], embeddings[i])
        would_exceed = current_len + 1 + len(sentence) > chunk_size

        if sim >= similarity_threshold and not would_exceed:
            current_sentences.append(sentence)
            current_len += 1 + len(sentence)
        else:
            chunks.append(" ".join(current_sentences))
            current_sentences = [sentence]
            current_len = len(sentence)

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks
