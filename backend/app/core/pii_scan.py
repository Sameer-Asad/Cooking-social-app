"""
Rule-based PII scan (regex + basic patterns) run on user.md content before
it's written to Postgres (Sec 11.2 — "PII / Sensitive Data Leakage...
run before user.md persists to Postgres", zero-tolerance target).

This is intentionally simple pattern-matching, not a full NER pipeline —
good enough to catch obvious leakage (emails, phone numbers, card-like
digit sequences) that an LLM summarizer might otherwise copy verbatim
from a conversation into the persistent memory file.
"""

import re

_PATTERNS = {
    # Order matters for redact(): card_like must run before phone, since
    # phone's shorter digit-group pattern can partially match inside a
    # card number and corrupt it before card_like's wider pattern runs.
    "card_like": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "phone": re.compile(
        r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"
    ),
}


def scan_for_pii(text: str) -> list[str]:
    """Returns a list of PII category names found in `text` (empty if clean)."""
    found = []
    for label, pattern in _PATTERNS.items():
        if pattern.search(text):
            found.append(label)
    return found


def redact(text: str) -> str:
    redacted = text
    for label, pattern in _PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED_{label.upper()}]", redacted)
    return redacted
