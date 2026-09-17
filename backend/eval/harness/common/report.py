"""
Shared result-aggregation + report-writing for every run_*.py script.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "results",
)


def save_report(category: str, metric_results: dict, meta: dict | None = None) -> str:
    """Writes eval/results/<timestamp>_<category>.json and returns the
    path. `metric_results` should be {metric_name: result_dict, ...}."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}_{category}.json"
    path = os.path.join(RESULTS_DIR, filename)

    report = {
        "category": category,
        "generated_at": timestamp,
        "meta": meta or {},
        "metrics": metric_results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n[{category}] report written to {path}")
    return path


def print_summary(category: str, metric_results: dict) -> None:
    print(f"\n=== {category.upper()} EVAL SUMMARY ===")
    for name, result in metric_results.items():
        if isinstance(result, dict):
            headline = {
                k: v
                for k, v in result.items()
                if k
                in (
                    "accuracy",
                    "precision",
                    "recall",
                    "f1",
                    "hit_rate",
                    "wer",
                    "cer",
                    "clean",
                    "score",
                )
            }
            print(f"  {name}: {headline or result}")
        else:
            print(f"  {name}: {result}")
