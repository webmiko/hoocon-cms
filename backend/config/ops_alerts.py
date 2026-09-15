"""Ops Telegram alerts for HTTP 5xx and external monitor scripts."""

from __future__ import annotations

import html
import os

from django.conf import settings
from django.core.cache import cache

from social.publishers import PublishResult, publish_telegram


def ops_telegram_chat_ids() -> list[str]:
    """Return configured ops chat ids (comma-separated env / settings)."""
    configured = getattr(settings, "OPS_TELEGRAM_CHAT_IDS", None)
    if configured:
        return [str(item).strip() for item in configured if str(item).strip()]
    raw = os.getenv("OPS_TELEGRAM_CHAT_IDS", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def ops_alert_dedup_seconds() -> int:
    """TTL for duplicate alert suppression."""
    return int(getattr(settings, "OPS_ALERT_DEDUP_SECONDS", 900))


def should_send_ops_alert(dedup_key: str) -> bool:
    """Return True when this alert key was not sent recently."""
    key = (dedup_key or "ops").strip() or "ops"
    cache_key = f"ops_alert:v1:{key}"
    return bool(cache.add(cache_key, 1, timeout=ops_alert_dedup_seconds()))


def format_ops_telegram_message(*, title: str, body: str) -> str:
    """HTML message for ops Telegram chats."""
    parts = [f"<b>{html.escape(title.strip())}</b>"]
    if body.strip():
        parts.append(html.escape(body.strip()))
    return "\n".join(parts)


def send_ops_telegram_alert(
    *,
    title: str,
    body: str,
    dedup_key: str,
) -> int:
    """Send an ops alert when dedup allows; return success count."""
    if not should_send_ops_alert(dedup_key):
        return 0
    chat_ids = ops_telegram_chat_ids()
    if not chat_ids:
        return 0
    text = format_ops_telegram_message(title=title, body=body)
    sent = 0
    for chat_id in chat_ids:
        result: PublishResult = publish_telegram(chat_id=chat_id, text=text)
        if result.ok:
            sent += 1
    return sent
