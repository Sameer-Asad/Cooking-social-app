"""
UUID(as_uuid=True) columns (models.py) require real uuid.UUID Python
objects for both inserts and query comparisons — SQLAlchemy's bind
processor for that type calls `.hex` on whatever it's given, which
raises AttributeError on a plain str.

IDs legitimately cross str boundaries in a few places (JWT `sub` claims,
Celery task args — UUID objects aren't JSON-serializable, so Celery
task args must be plain strings). This helper is the one place that
converts back to uuid.UUID right before the value touches the ORM.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException


def to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid ID format")
