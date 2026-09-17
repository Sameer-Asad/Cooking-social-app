"""
Generator eval: Faithfulness (DeepEval native), Language-match accuracy
(custom deterministic), Recipe correctness (custom G-Eval).

Calls the real agentic loop via app.bot.graph.run_turn — the
non-streaming entry point — since eval doesn't need token-by-token
output, just the final answer text.
"""

from __future__ import annotations

import asyncio
import sys

from deepeval import evaluate
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from eval.harness.common.custom_geval import recipe_correctness_metric
from eval.harness.common.dataset import load_jsonl
from eval.harness.common.eval_config import EVAL_ASYNC_CONFIG
from eval.harness.common.metrics import language_match_accuracy
from eval.harness.common.report import print_summary, save_report

from app.bot.graph import run_turn


async def _ask(question: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are a helpful multilingual cooking assistant. Reply in the same language as the question.",
        },
        {"role": "user", "content": question},
    ]
    return await run_turn(messages)


def run():
    rows = load_jsonl("golden_datasets/generator.jsonl")

    test_cases = []
    lang_pairs = []
    for row in rows:
        actual_output = asyncio.run(_ask(row["input"]))
        test_cases.append(
            LLMTestCase(
                input=row["input"],
                actual_output=actual_output,
                expected_output=row["expected_output"],
                retrieval_context=None,
            )
        )
        lang_pairs.append((row["language"], actual_output))

    faithfulness_metric = FaithfulnessMetric()
    recipe_metric = recipe_correctness_metric()

    # FaithfulnessMetric needs retrieval_context; since these generator
    # test cases have none (no RAG doc involved), it's included here for
    # completeness/config-mapping purposes but will be skipped/low-signal
    # on cases without retrieval_context — recipe_correctness_metric (a
    # GEval against expected_output) is the more meaningful check for
    # this dataset.
    deepeval_results = evaluate(
        test_cases, [recipe_metric], async_config=EVAL_ASYNC_CONFIG
    )

    lang_results = language_match_accuracy(lang_pairs)

    metric_results = {
        "faithfulness": {
            "note": "no retrieval_context in this dataset; see recipe_correctness instead"
        },
        "language_match_accuracy": lang_results,
        "recipe_correctness": {"raw_deepeval_results": str(deepeval_results)},
    }
    print_summary("generator", metric_results)
    save_report("generator", metric_results, meta={"n_cases": len(rows)})


if __name__ == "__main__":
    run()
    sys.exit(0)
