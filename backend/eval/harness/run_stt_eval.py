"""
STT eval: WER/CER via jiwer, Language-detection accuracy,
Confidence calibration — all custom deterministic, no LLM judge.

Requires actual audio files under golden_datasets/stt/audio/ matching
the audio_path field in transcripts.jsonl — these are NOT included
(can't synthesize real human speech here). See eval/README.md.
"""

from __future__ import annotations

import os
import sys

from eval.harness.common.dataset import load_jsonl
from eval.harness.common.metrics import (
    compute_wer_cer,
    confidence_calibration,
    language_detection_accuracy,
)
from eval.harness.common.report import print_summary, save_report

from app.bot.stt import transcribe

AUDIO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "golden_datasets",
    "stt",
    "audio",
)


async def _transcribe(audio_path: str, language_hint: str | None = None):
    return await transcribe(audio_path, language_hint=language_hint)


def run():
    import asyncio

    rows = load_jsonl("golden_datasets/stt/transcripts.jsonl")

    wer_pairs = []
    lang_pairs = []
    calibration_records = []
    skipped = []

    for row in rows:
        full_path = os.path.join(AUDIO_DIR, os.path.basename(row["audio_path"]))
        if not os.path.exists(full_path):
            skipped.append(row["id"])
            continue

        result = asyncio.run(_transcribe(full_path))
        wer_pairs.append((row["ground_truth_text"], result.text))
        lang_pairs.append((row["language"], result.detected_language))

        pair_wer = compute_wer_cer([(row["ground_truth_text"], result.text)])["wer"]
        calibration_records.append(
            {"confidence": result.language_confidence, "wer": pair_wer}
        )

    if skipped:
        print(f"Skipped {len(skipped)} rows — audio file missing: {skipped}")

    metric_results = {
        "wer_per_language": compute_wer_cer(wer_pairs)
        if wer_pairs
        else {"note": "no audio files found — see eval/README.md"},
        "language_detection_accuracy": language_detection_accuracy(lang_pairs)
        if lang_pairs
        else {"note": "no audio files found"},
        "confidence_calibration": confidence_calibration(calibration_records)
        if calibration_records
        else {"note": "no audio files found"},
        "skipped_missing_audio": skipped,
    }
    print_summary("stt", metric_results)
    save_report(
        "stt",
        metric_results,
        meta={"n_cases": len(rows), "n_evaluated": len(wer_pairs)},
    )


if __name__ == "__main__":
    run()
    sys.exit(0)
