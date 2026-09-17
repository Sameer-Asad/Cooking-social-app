from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.billing.lemonsqueezy import (
    LemonSqueezyNotConfigured,
    create_checkout_url,
    verify_webhook_signature,
)
from app.core.ids import to_uuid
from app.models.models import User

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
async def create_checkout(user: User = Depends(get_current_user)):
    try:
        url = await create_checkout_url(str(user.id), user.email)
    except LemonSqueezyNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"checkout_url": url}


@router.post("/webhook")
async def lemonsqueezy_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Lemon Squeezy calls this on subscription lifecycle events. Signature
    verification must run on the raw request body — not the parsed JSON —
    since re-serializing JSON can change byte-for-byte formatting and
    break the HMAC comparison."""
    raw_body = await request.body()
    signature = request.headers.get("X-Signature")

    if not verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event_name = payload.get("meta", {}).get("event_name")
    custom_data = payload.get("meta", {}).get("custom_data", {})
    user_id = custom_data.get("user_id")

    if not user_id:
        # Nothing we can attribute this event to — ack without erroring so
        # Lemon Squeezy doesn't retry indefinitely on an event we can't use.
        return {"ok": True, "note": "no user_id in custom_data"}

    result = await db.execute(select(User).where(User.id == to_uuid(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        return {"ok": True, "note": "user not found"}

    if event_name in (
        "subscription_created",
        "subscription_updated",
        "subscription_resumed",
    ):
        status_value = payload.get("data", {}).get("attributes", {}).get("status")
        # Lemon Squeezy subscription statuses: "on_trial", "active",
        # "paused", "past_due", "unpaid", "cancelled", "expired".
        user.is_paid_tier = status_value in ("on_trial", "active")
        await db.commit()
    elif event_name in ("subscription_cancelled", "subscription_expired"):
        user.is_paid_tier = False
        await db.commit()

    return {"ok": True}
