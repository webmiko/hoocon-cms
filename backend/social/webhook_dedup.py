"""Idempotency for inbound Telegram/MAX webhook updates (retry dedup)."""

from __future__ import annotations

from typing import Any

from django.core.cache import cache

_DEDUP_TTL_SECONDS = 24 * 60 * 60


def webhook_dedup_key(channel: str, update: dict[str, Any]) -> str | None:
    """Build a stable cache key for one messenger update, or None if unknown."""
    if channel == "telegram":
        update_id = update.get("update_id")
        if update_id is not None:
            return f"telegram:{update_id}"
        return None

    if channel == "max":
        update_type = (update.get("update_type") or "").strip()
        if not update_type:
            return None
        message = update.get("message")
        if isinstance(message, dict):
            body = message.get("body")
            if isinstance(body, dict):
                mid = (body.get("mid") or "").strip()
                if mid:
                    return f"max:{update_type}:{mid}"
        user = update.get("user")
        if not isinstance(user, dict):
            message = update.get("message")
            if isinstance(message, dict):
                sender = message.get("sender")
                if isinstance(sender, dict):
                    user = sender
        user_id = user.get("user_id") if isinstance(user, dict) else None
        timestamp = update.get("timestamp")
        if user_id is not None and timestamp is not None:
            return f"max:{update_type}:{user_id}:{timestamp}"
        return None

    return None


def begin_webhook_processing(channel: str, update: dict[str, Any]) -> bool:
    """Return True when this update should be processed (first time in TTL window)."""
    key = webhook_dedup_key(channel, update)
    if not key:
        return True
    cache_key = f"webhook_dedup:v1:{key}"
    return bool(cache.add(cache_key, 1, timeout=_DEDUP_TTL_SECONDS))
