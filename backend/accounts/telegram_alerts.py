"""Staff Telegram alert recipients and send helpers."""

from __future__ import annotations

import html
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet

from accounts.roles import GROUP_MANAGER
from social.publishers import PublishResult, publish_telegram

User = get_user_model()


def staff_telegram_recipients_managers(*, lead_assignee_id: int | None = None) -> QuerySet[Any]:
    """Active managers with Telegram alerts (optionally prefer lead assignee).

    When ``lead_assignee_id`` is set and that user is a reachable manager,
    only they are returned (plus callers may union superusers separately).
    Otherwise all managers in group «Менеджер» with a chat id.
    """
    base = (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            groups__name=GROUP_MANAGER,
            telegram_profile__telegram_alerts_enabled=True,
        )
        .exclude(telegram_profile__telegram_chat_id="")
        .distinct()
    )
    if lead_assignee_id is not None:
        assigned = base.filter(pk=lead_assignee_id)
        if assigned.exists():
            return assigned
    return base.order_by("pk")


def staff_telegram_recipients_superusers() -> QuerySet[Any]:
    """Active superusers with Telegram alerts enabled and a chat id."""
    return (
        User.objects.filter(
            is_active=True,
            is_superuser=True,
            telegram_profile__telegram_alerts_enabled=True,
        )
        .exclude(telegram_profile__telegram_chat_id="")
        .order_by("pk")
    )


def telegram_chat_id_for(user: AbstractBaseUser) -> str:
    """Return trimmed chat id or empty string."""
    profile = getattr(user, "telegram_profile", None)
    if profile is None:
        return ""
    if not getattr(profile, "telegram_alerts_enabled", False):
        return ""
    return (getattr(profile, "telegram_chat_id", "") or "").strip()


def user_has_staff_webpush(user: AbstractBaseUser) -> bool:
    """True when the user has an active Admin PWA push subscription.

    Policy: email always; Web Push is an extra channel; Telegram is a
    fallback only when push is not connected.
    """
    user_id = getattr(user, "pk", None)
    if not user_id:
        return False
    from webpush.models import PushSubscription

    return PushSubscription.objects.filter(
        user_id=user_id,
        topic_support=True,
        user__is_staff=True,
        user__is_active=True,
    ).exists()


def without_staff_webpush(users: QuerySet[Any] | list[Any]) -> list[Any]:
    """Keep only recipients who do not have staff Web Push (Telegram fallback)."""
    return [user for user in users if not user_has_staff_webpush(user)]


def send_telegram_to_users(users: QuerySet[Any] | list[Any], text: str) -> int:
    """Send HTML text to each user's Telegram chat; return success count."""
    body = (text or "").strip()
    if not body:
        return 0
    sent = 0
    seen: set[str] = set()
    for user in users:
        chat_id = telegram_chat_id_for(user)
        if not chat_id or chat_id in seen:
            continue
        seen.add(chat_id)
        result: PublishResult = publish_telegram(chat_id=chat_id, text=body)
        if result.ok:
            sent += 1
    return sent


def format_staff_telegram_message(*, title: str, body: str, url: str = "") -> str:
    """Compose Telegram HTML message with optional Admin deep link."""
    from django.conf import settings

    parts = [f"<b>{html.escape(title)}</b>", html.escape(body)]
    path = (url or "").strip()
    if path:
        site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
        if path.startswith("http"):
            link = path
        else:
            link = f"{site}{path if path.startswith('/') else '/' + path}"
        parts.append(f'<a href="{html.escape(link)}">Открыть в Admin</a>')
    return "\n".join(parts)
