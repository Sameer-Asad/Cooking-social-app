"""
Optional document RAG (Sec 4.5) — hybrid dense + sparse search on Qdrant
Cloud, scoped to one collection per user. Only used when the user has
uploaded a document and opted in for the session.

API surface confirmed against qdrant-client's documented models:
QdrantClient.create_collection / upsert / query_points, with
models.Prefetch + models.FusionQuery(fusion=models.Fusion.RRF) for
reciprocal-rank-fusion hybrid search.
"""

from __future__ import annotations

from collections import Counter

from groq import AsyncGroq
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from langsmith import traceable

from app.config import settings

DENSE_MODEL_NAME = "all-MiniLM-L6-v2"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

_client: QdrantClient | None = None
_dense_model: SentenceTransformer | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return _client


def get_dense_model() -> SentenceTransformer:
    global _dense_model
    if _dense_model is None:
        _dense_model = SentenceTransformer(DENSE_MODEL_NAME)
    return _dense_model


def _collection_name(user_id: str) -> str:
    return f"user_docs_{user_id}"


def _sparse_vector(text: str) -> models.SparseVector:
    """Simplified BM25-style sparse vector: hashed term -> term frequency.
    Good enough for keyword-overlap signal in the RRF fusion; a proper
    BM25/SPLADE encoder can replace this without changing the rest of
    the pipeline, since only this function would need to change."""
    words = [w.lower() for w in text.split() if w.strip()]
    counts = Counter(words)
    indices = [hash(word) % (2**31) for word in counts]
    values = [float(c) for c in counts.values()]
    return models.SparseVector(indices=indices, values=values)


def ensure_collection(user_id: str, *, recreate: bool = False) -> None:
    client = get_client()
    name = _collection_name(user_id)
    if recreate and client.collection_exists(name):
        client.delete_collection(name)
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=384, distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )


@traceable(name="rag_index_document_chunks")
def index_chunks(user_id: str, chunks: list[str]) -> None:
    # Sec 4.5 supports one active document per user at a time (see
    # routes_rag.py) — recreate the collection on every upload so a
    # shorter re-upload doesn't leave stale higher-numbered points from
    # a previous, longer document mixed into hybrid_search results.
    ensure_collection(user_id, recreate=True)
    client = get_client()
    dense_model = get_dense_model()
    dense_vectors = dense_model.encode(chunks)

    points = [
        models.PointStruct(
            id=i,
            vector={
                DENSE_VECTOR_NAME: dense_vectors[i].tolist(),
                SPARSE_VECTOR_NAME: _sparse_vector(chunk),
            },
            payload={"text": chunk},
        )
        for i, chunk in enumerate(chunks)
    ]
    client.upsert(collection_name=_collection_name(user_id), points=points)


@traceable(name="rag_hybrid_search")
def hybrid_search(user_id: str, query: str, top_k: int = 5) -> list[str]:
    client = get_client()
    dense_model = get_dense_model()
    dense_query = dense_model.encode(query).tolist()
    sparse_query = _sparse_vector(query)

    results = client.query_points(
        collection_name=_collection_name(user_id),
        prefetch=[
            models.Prefetch(query=dense_query, using=DENSE_VECTOR_NAME, limit=20),
            models.Prefetch(query=sparse_query, using=SPARSE_VECTOR_NAME, limit=20),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_k,
    )
    return [point.payload["text"] for point in results.points]


_RAG_SUMMARY_SYSTEM_PROMPT = """\
You are given several excerpts retrieved from a document the user
uploaded, plus the user's current question. Summarize the excerpts into
ONE concise paragraph containing only the information relevant to
answering the question. Do not answer the question yourself — just
produce the summarized context. If the excerpts don't actually address
the question, say so briefly rather than inventing relevance.
"""


@traceable(name="rag_summarize_chunks")
async def summarize_chunks(chunks: list[str], query: str) -> str:
    """Condenses the top-k retrieved chunks into one paragraph before
    they enter the main agent's context (Sec 4.5) — keeps the main
    context lean instead of dumping all 5 raw chunks in verbatim."""
    if not chunks:
        return ""

    client = AsyncGroq(api_key=settings.groq_api_key)
    excerpts = "\n\n---\n\n".join(chunks)
    completion = await client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": _RAG_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"QUESTION: {query}\n\nEXCERPTS:\n{excerpts}"},
        ],
        temperature=0.2,
    )
    return completion.choices[0].message.content.strip()
