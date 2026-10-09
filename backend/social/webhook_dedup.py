"""Idempotency for inbound Telegram/MAX webhook updates (retry dedup).

An update is marked *done* only after its handler succeeds. While it runs, a
short lock keeps a concurrent redelivery out; a failure releases the lock so
Celery autoretry (or the messenger's own retry) can process it again.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.core.cache import cache

_DONE_TTL_SECONDS = 24 * 60 * 60
_LOCK_TTL_SECONDS = 5 * 60
_PREFIX = "webhook_dedup:v2"


def _max_user_id(update: dict[str, Any]) -> object:
    for holder in (update, update.get("callback"), update.get("message")):
        if not isinstance(holder, dict):
            continue
        for field in ("user", "sender"):
            user = holder.get(field)
            if isinstance(user, dict) and user.get("user_id") is not None:
                return user["user_id"]
    return None


def webhook_dedup_key(channel: str, update: dict[str, Any]) -> str | None:
    """Build a stable cache key for one messenger update, or None if unknown."""
    if channel == "telegram":
        update_id = update.get("update_id")
        return f"telegram:{update_id}" if update_id is not None else None

    if channel != "max":
        return None
    update_type = (update.get("update_type") or "").strip()
    if not update_type:
        return None
    # A button tap carries the *bot* message it belongs to: key on the tap.
    callback = update.get("callback")
    if isinstance(callback, dict):
        callback_id = str(callback.get("callback_id") or "").strip()
        if callback_id:
            return f"max:{update_type}:cb:{callback_id}"
    message = update.get("message")
    body = message.get("body") if isinstance(message, dict) else None
    if isinstance(body, dict):
        mid = str(body.get("mid") or "").strip()
        if mid:
            return f"max:{update_type}:{mid}"
    user_id = _max_user_id(update)
    timestamp = update.get("timestamp")
    if user_id is not None and timestamp is not None:
        return f"max:{update_type}:{user_id}:{timestamp}"
    return None


@contextmanager
def webhook_once(channel: str, update: dict[str, Any]) -> Iterator[bool]:
    """Yield True when this update should be handled now.

    False means it already succeeded or another worker is handling it.
    Exceptions from the body propagate and leave the update retryable.
    """
    key = webhook_dedup_key(channel, update)
    if not key:
        yield True
        return
    done_key, lock_key = f"{_PREFIX}:done:{key}", f"{_PREFIX}:lock:{key}"
    if cache.get(done_key) or not cache.add(lock_key, 1, timeout=_LOCK_TTL_SECONDS):
        yield False
        return
    try:
        yield True
    except BaseException:
        cache.delete(lock_key)
        raise
    cache.set(done_key, 1, timeout=_DONE_TTL_SECONDS)
    cache.delete(lock_key)
