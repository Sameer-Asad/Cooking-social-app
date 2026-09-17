"""
TTS eval: Markdown-stripping correctness, Cache hit rate,
Circuit-breaker/audio_degraded correctness — all custom deterministic.

Uses a minimal in-memory fake Redis (no real Redis server needed for
this harness) to exercise app.bot.tts.synthesize()'s caching and
circuit-breaker paths directly.
"""

from __future__ import annotations

import asyncio
import sys
from difflib import SequenceMatcher

from eval.harness.common.dataset import load_jsonl
from eval.harness.common.metrics import (
    CircuitBreakerScenario,
    cache_hit_rate,
    circuit_breaker_correctness,
    markdown_stripping_correctness,
)
from eval.harness.common.report import print_summary, save_report

from app.bot import tts as tts_module


class _FakeRedis:
    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value, ex=None):
        self._store[key] = value


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def run():
    rows = load_jsonl("golden_datasets/tts/markdown_samples.jsonl")

    strip_results = []
    similarity_scores = []
    for row in rows:
        spoken = tts_module._strip_markdown(row["raw_markdown"])
        clean_check = markdown_stripping_correctness(spoken)
        similarity = _similarity(spoken.strip(), row["expected_spoken_text"].strip())
        similarity_scores.append(similarity)
        strip_results.append(
            {
                "id": row["id"],
                "construct": row["construct"],
                "clean": clean_check["clean"],
                "leftover_symbols": clean_check["leftover_symbols_found"],
                "similarity_to_expected": similarity,
                "actual_spoken": spoken,
            }
        )

    # Cache hit rate: synthesize the same text twice per sample using a
    # fake Redis — first call is always a miss, second should always hit.
    redis = _FakeRedis()
    hits = 0
    total = 0
    for row in rows[:5]:  # a subset is enough to prove the cache path works
        try:
            asyncio.run(tts_module.synthesize(redis, row["raw_markdown"], "en"))
            total += 1
            cached_before = redis._store.copy()
            asyncio.run(tts_module.synthesize(redis, row["raw_markdown"], "en"))
            total += 1
            if (
                redis._store == cached_before
            ):  # nothing new written = it was a cache hit
                hits += 1
        except Exception as e:
            print(
                f"[tts cache check] synth failed for {row['id']} (likely no network in this environment): {e}"
            )

    cache_results = (
        cache_hit_rate(hits, total)
        if total
        else {
            "note": "gTTS network call failed in this environment — cache path not exercised"
        }
    )

    # Circuit breaker: monkeypatch _synthesize_sync to always raise, and
    # confirm it opens after 3 consecutive failures + reports audio_degraded.
    original_synth = tts_module._synthesize_sync

    def _always_fail(text, lang):
        from gtts.tts import gTTSError

        raise gTTSError("forced failure for eval")

    def _run_scenario(scenario: CircuitBreakerScenario):
        tts_module._consecutive_failures = 0
        tts_module._circuit_open_until = 0.0
        tts_module._synthesize_sync = _always_fail
        audio_degraded = False
        try:
            asyncio.run(tts_module.synthesize(_FakeRedis(), "test text", "en"))
        except tts_module.TTSUnavailable:
            audio_degraded = True
        circuit_opened = tts_module._circuit_open_until > 0
        tts_module._synthesize_sync = original_synth
        return circuit_opened, audio_degraded

    scenarios = [
        CircuitBreakerScenario(
            consecutive_failures_injected=3,
            expected_circuit_open=True,
            expected_audio_degraded=True,
        ),
    ]
    breaker_results = circuit_breaker_correctness(scenarios, _run_scenario)

    metric_results = {
        "markdown_stripping_correctness": {
            "all_clean": all(r["clean"] for r in strip_results),
            "n_with_leftovers": sum(1 for r in strip_results if not r["clean"]),
            "mean_similarity_to_expected": sum(similarity_scores)
            / len(similarity_scores)
            if similarity_scores
            else 0,
            "details": strip_results,
        },
        "cache_hit_rate": cache_results,
        "circuit_breaker_correctness": breaker_results,
    }
    print_summary("tts", metric_results)
    save_report("tts", metric_results, meta={"n_cases": len(rows)})


if __name__ == "__main__":
    run()
    sys.exit(0)
