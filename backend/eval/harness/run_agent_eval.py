"""
Agent eval: Tool-selection accuracy, Tool-call success rate (DeepEval
native), Loop termination rate (custom deterministic).

Drives the real streaming agent loop (app.bot.graph.run_turn_stream) and
records which tools it actually called ("status" events) plus how many
agent<->tool round-trips the turn took, against the 5-round-trip cap.
"""

from __future__ import annotations

import asyncio
import sys

from deepeval import evaluate
from deepeval.metrics import ArgumentCorrectnessMetric, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase, ToolCall

from eval.harness.common.dataset import load_jsonl
from eval.harness.common.eval_config import EVAL_ASYNC_CONFIG
from eval.harness.common.metrics import loop_termination_rate
from eval.harness.common.report import print_summary, save_report

from app.bot.graph import run_turn_stream


async def _run_agent(question: str) -> tuple[str, list[str], int]:
    """Returns (final_text, tools_called_names, round_trip_count)."""
    messages = [
        {
            "role": "system",
            "content": "You are a helpful cooking assistant with access to tools. Use web_search sparingly, only for obscure/regional dishes you're not confident about.",
        },
        {"role": "user", "content": question},
    ]
    tools_called: list[str] = []
    round_trips = 0
    final_text = ""
    async for event in run_turn_stream(messages):
        if event["type"] == "status":
            tools_called.append(event["tool"])
            round_trips += 1
        elif event["type"] == "final":
            final_text = event["text"]
    return final_text, tools_called, round_trips


def run():
    rows = load_jsonl("golden_datasets/agent.jsonl")

    test_cases = []
    round_trip_counts = []
    for row in rows:
        final_text, tools_called, round_trips = asyncio.run(_run_agent(row["input"]))
        round_trip_counts.append(round_trips)
        test_cases.append(
            LLMTestCase(
                input=row["input"],
                actual_output=final_text,
                tools_called=[ToolCall(name=t) for t in tools_called],
                expected_tools=[ToolCall(name=t) for t in row["expected_tools"]],
            )
        )

    tool_correctness = ToolCorrectnessMetric()
    argument_correctness = ArgumentCorrectnessMetric()

    deepeval_results = evaluate(
        test_cases,
        [tool_correctness, argument_correctness],
        async_config=EVAL_ASYNC_CONFIG,
    )
    loop_results = loop_termination_rate(round_trip_counts, cap=5)

    metric_results = {
        "tool_selection_accuracy": {"raw_deepeval_results": str(deepeval_results)},
        "tool_call_success_rate": {"raw_deepeval_results": str(deepeval_results)},
        "loop_termination_rate": loop_results,
    }
    print_summary("agent", metric_results)
    save_report("agent", metric_results, meta={"n_cases": len(rows)})


if __name__ == "__main__":
    run()
    sys.exit(0)
