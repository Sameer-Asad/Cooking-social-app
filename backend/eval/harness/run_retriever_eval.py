"""
Retriever eval: Context Precision, Context Recall (DeepEval native),
Retrieval latency p95 (custom deterministic).

Actually indexes each test case's retrieval_context into a real Qdrant
collection (index_chunks) before calling hybrid_search — otherwise this
harness would only ever be testing DeepEval's scoring logic against the
dataset's own answer key, never the real retriever. Each row gets its
own throwaway user_id so cases can't pollute each other, and
ensure_collection(recreate=True) inside index_chunks wipes any stale
state from a prior run of the same row.
"""

from __future__ import annotations

import sys

from deepeval import evaluate
from deepeval.metrics import ContextualPrecisionMetric, ContextualRecallMetric
from deepeval.test_case import LLMTestCase

from eval.harness.common.dataset import load_jsonl
from eval.harness.common.eval_config import EVAL_ASYNC_CONFIG
from eval.harness.common.metrics import measure_retrieval_latency
from eval.harness.common.report import print_summary, save_report

try:
    from app.bot.rag.qdrant_client import hybrid_search, index_chunks

    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False


def _row_user_id(row: dict) -> str:
    return f"eval-retriever-{row['id']}"


def _expected_output_text(row: dict) -> str:
    """The actual TEXT of the chunk(s) listed in expected_context_ids —
    not the bare IDs themselves, since ContextualPrecision/Recall judge
    content similarity, not ID equality. Each retrieval_context entry is
    formatted as "<id>: <text>" in this dataset, so the id is recovered
    by splitting on the first ':'."""
    wanted_ids = set(row["expected_context_ids"])
    matches = []
    for chunk in row["retrieval_context"]:
        chunk_id, _, text = chunk.partition(":")
        if chunk_id.strip() in wanted_ids:
            matches.append(text.strip())
    return " ".join(matches) if matches else row["retrieval_context"][0]


def _real_retrieve(row: dict) -> list[str] | None:
    """Indexes this row's chunks into a scratch collection, then really
    searches it. Returns None (triggering the dataset fallback) if RAG
    isn't importable, misconfigured (missing qdrant_url/api_key), or the
    live service is unreachable — any of those should degrade the
    harness gracefully rather than crashing the whole eval run."""
    if not _RAG_AVAILABLE:
        return None
    user_id = _row_user_id(row)
    try:
        index_chunks(user_id, row["retrieval_context"])
        return hybrid_search(user_id, row["input"])
    except Exception as exc:
        print(
            f"[{row['id']}] real hybrid_search unavailable ({exc}); falling back to dataset retrieval_context."
        )
        return None


def run():
    rows = load_jsonl("golden_datasets/retriever.jsonl")

    test_cases = []
    latency_queries = []
    used_real_retriever = 0

    for row in rows:
        actual_context = _real_retrieve(row)
        if actual_context is not None:
            used_real_retriever += 1
        retrieval_context = (
            actual_context if actual_context is not None else row["retrieval_context"]
        )

        test_cases.append(
            LLMTestCase(
                input=row["input"],
                actual_output="",  # precision/recall score the chunks, not a generated answer
                retrieval_context=retrieval_context,
                expected_output=_expected_output_text(row),
            )
        )
        latency_queries.append(row)

    precision_metric = ContextualPrecisionMetric()
    recall_metric = ContextualRecallMetric()
    deepeval_results = evaluate(
        test_cases, [precision_metric, recall_metric], async_config=EVAL_ASYNC_CONFIG
    )

    if used_real_retriever:
        latency = measure_retrieval_latency(
            lambda q: hybrid_search(
                _row_user_id(next(r for r in rows if r["input"] == q)), q
            ),
            [r["input"] for r in rows],
            repeat=1,
        )
    else:
        latency = {
            "note": "real hybrid_search unavailable for every row — latency not measured, see logged reasons above"
        }

    metric_results = {
        "context_precision": {"raw_deepeval_results": str(deepeval_results)},
        "context_recall": {"raw_deepeval_results": str(deepeval_results)},
        "retrieval_latency_p95": latency,
    }
    print_summary("retriever", metric_results)
    save_report(
        "retriever",
        metric_results,
        meta={"n_cases": len(rows), "n_used_real_retriever": used_real_retriever},
    )


if __name__ == "__main__":
    run()
    sys.exit(0)
