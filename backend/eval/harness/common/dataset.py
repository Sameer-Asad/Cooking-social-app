from __future__ import annotations

import json
import os

BACKEND_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def load_jsonl(relative_path: str) -> list[dict]:
    """`relative_path` is relative to eval/, e.g. 'golden_datasets/agent.jsonl'."""
    path = os.path.join(BACKEND_ROOT, relative_path)
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
