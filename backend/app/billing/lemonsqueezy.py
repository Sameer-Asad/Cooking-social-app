"""
Minimal Lemon Squeezy integration — no official Python SDK exists, so
this calls their documented REST API directly with httpx (already a
project dependency) and verifies webhook signatures with stdlib hmac.
Docs: https://docs.lemonsqueezy.com/api
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from app.config import settings

_API_BASE = "https://api.lemonsqueezy.com/v1"


class LemonSqueezyNotConfigured(Exception):
    """Raised when required Lemon Squeezy env vars aren't set yet."""


def _require_configured() -> None:
    missing = [
        name
        for name, value in [
            ("LEMONSQUEEZY_API_KEY", settings.lemonsqueezy_api_key),
            ("LEMONSQUEEZY_STORE_ID", settings.lemonsqueezy_store_id),
            ("LEMONSQUEEZY_PRO_VARIANT_ID", settings.lemonsqueezy_pro_variant_id),
        ]
        if not value
    ]
    if missing:
        raise LemonSqueezyNotConfigured(
            f"Missing Lemon Squeezy config: {', '.join(missing)}. "
            "Set these in .env after creating a store/product in your "
            "Lemon Squeezy dashboard."
        )


async def create_checkout_url(user_id: str, user_email: str) -> str:
    """Creates a hosted Checkout session for the Pro plan and returns its
    URL. `user_id` is embedded as custom data so the webhook handler can
    identify which user a subscription event belongs to."""
    _require_configured()

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user_email,
                    "custom": {"user_id": user_id},
                },
                "product_options": {
                    "redirect_url": f"{settings.frontend_base_url}?upgraded=1",
                },
            },
            "relationships": {
                "store": {
                    "data": {"type": "stores", "id": settings.lemonsqueezy_store_id}
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": settings.lemonsqueezy_pro_variant_id,
                    }
                },
            },
        }
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{_API_BASE}/checkouts",
            json=payload,
            headers={
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
                "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
            },
        )
        response.raise_for_status()
        data = response.json()

    return data["data"]["attributes"]["url"]


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Lemon Squeezy signs webhook payloads with HMAC-SHA256 using your
    configured webhook secret, sent in the X-Signature header."""
    if not signature_header or not settings.lemonsqueezy_webhook_secret:
        return False
    expected = hmac.new(
        settings.lemonsqueezy_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
