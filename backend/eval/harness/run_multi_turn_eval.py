"""
Multi-turn eval: Context retention (DeepEval native, ConversationalTestCase),
Block-summary fidelity (custom G-Eval, reuses the REAL summarization
function), Cross-session continuity (custom G-Eval).

Handles three row shapes from multi_turn.jsonl by `test_focus`:
  - context_retention / contradiction_catch / reference_resolution:
    generate the final assistant turn given the scripted history, then
    score with KnowledgeRetentionMetric.
  - block_boundary_summary: exercises the REAL block-summarization logic
    (app.api.routes_bot._summarize_new_block_if_any) against 7+ fake
    messages built from the scripted turns, then scores the generated
    summary's fidelity with a custom G-Eval.
  - cross_session_continuity: generates a reply with `prior_session_memory_md`
    injected as the "remembered" system context, then scores whether the
    reply actually draws on it.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from deepeval import evaluate
from deepeval.metrics import KnowledgeRetentionMetric
from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn

from eval.harness.common.custom_geval import (
    block_summary_fidelity_metric,
    cross_session_continuity_metric,
)
from eval.harness.common.dataset import load_jsonl
from eval.harness.common.eval_config import EVAL_ASYNC_CONFIG
from eval.harness.common.report import print_summary, save_report

from app.bot.graph import run_turn

try:
    from app.api.routes_bot import _block_summary_cache, _summarize_new_block_if_any
except ImportError:
    _summarize_new_block_if_any = None
    _block_summary_cache = {}


async def _generate_final_turn(turns: list[dict], extra_system: str = "") -> str:
    system = "You are a helpful cooking assistant. Maintain consistency with everything the user has told you in this conversation."
    if extra_system:
        system += "\n" + extra_system
    messages = [{"role": "system", "content": system}]
    for t in turns:
        messages.append({"role": t["role"], "content": t["content"]})
    return await run_turn(messages)


def run():
    rows = load_jsonl("golden_datasets/multi_turn.jsonl")

    retention_cases = []
    fidelity_cases = []
    continuity_cases = []

    for row in rows:
        focus = row["test_focus"]

        if focus == "block_boundary_summary":
            if _summarize_new_block_if_any is None:
                print(
                    f"[{row['id']}] skipped — app.api.routes_bot._summarize_new_block_if_any not importable"
                )
                continue
            fake_messages = [
                SimpleNamespace(role=t["role"], content=t["content"])
                for t in row["turns"]
            ]
            # Pad to a full 7-message block if the scripted turns don't
            # already hit the boundary, so newly_frozen_block() actually fires.
            while len(fake_messages) < 7:
                fake_messages.append(
                    SimpleNamespace(role="user", content="(filler turn)")
                )
            conv_id = f"eval-{row['id']}"
            asyncio.run(
                _summarize_new_block_if_any(conv_id, fake_messages[:0], fake_messages)
            )
            summary = _block_summary_cache.get(conv_id, {}).get(0, "")
            raw_facts = "\n".join(f"{t['role']}: {t['content']}" for t in row["turns"])
            fidelity_cases.append(
                LLMTestCase(
                    input="",
                    actual_output=summary or "(no summary generated)",
                    expected_output=raw_facts,
                )
            )
            continue

        if focus == "cross_session_continuity":
            memory = row["prior_session_memory_md"]
            reply = asyncio.run(
                _generate_final_turn(
                    row["turns"],
                    extra_system=f"What you remember about this user from past sessions:\n{memory}",
                )
            )
            continuity_cases.append(
                LLMTestCase(
                    input=row["turns"][-1]["content"],
                    actual_output=reply,
                    context=[memory],
                )
            )
            continue

        # context_retention / contradiction_catch / reference_resolution
        reply = asyncio.run(_generate_final_turn(row["turns"]))
        conv_turns = [Turn(role=t["role"], content=t["content"]) for t in row["turns"]]
        conv_turns.append(Turn(role="assistant", content=reply))
        retention_cases.append(ConversationalTestCase(turns=conv_turns))

    knowledge_retention_results = None
    if retention_cases:
        knowledge_retention_results = evaluate(
            retention_cases,
            [KnowledgeRetentionMetric()],
            async_config=EVAL_ASYNC_CONFIG,
        )

    fidelity_results = None
    if fidelity_cases:
        fidelity_results = evaluate(
            fidelity_cases,
            [block_summary_fidelity_metric()],
            async_config=EVAL_ASYNC_CONFIG,
        )

    continuity_results = None
    if continuity_cases:
        continuity_results = evaluate(
            continuity_cases,
            [cross_session_continuity_metric()],
            async_config=EVAL_ASYNC_CONFIG,
        )

    metric_results = {
        "context_retention": {
            "raw_deepeval_results": str(knowledge_retention_results),
            "n": len(retention_cases),
        },
        "block_summary_fidelity": {
            "raw_deepeval_results": str(fidelity_results),
            "n": len(fidelity_cases),
        },
        "cross_session_continuity": {
            "raw_deepeval_results": str(continuity_results),
            "n": len(continuity_cases),
        },
    }
    print_summary("multi_turn", metric_results)
    save_report("multi_turn", metric_results, meta={"n_cases": len(rows)})


if __name__ == "__main__":
    run()
    sys.exit(0)
