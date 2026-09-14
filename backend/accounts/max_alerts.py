"""Staff MAX alert recipients and send helpers."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet

from accounts.roles import GROUP_MANAGER
from social.publishers import PublishResult, publish_max

User = get_user_model()


def staff_max_recipients_managers(*, lead_assignee_id: int | None = None) -> QuerySet[Any]:
    """Active managers with MAX alerts (optionally prefer lead assignee)."""
    base = (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            groups__name=GROUP_MANAGER,
            max_profile__max_alerts_enabled=True,
        )
        .exclude(max_profile__max_user_id="")
        .distinct()
    )
    if lead_assignee_id is not None:
        assigned = base.filter(pk=lead_assignee_id)
        if assigned.exists():
            return assigned
    return base.order_by("pk")


def staff_max_recipients_superusers() -> QuerySet[Any]:
    """Active superusers with MAX alerts enabled and a user id."""
    return (
        User.objects.filter(
            is_active=True,
            is_superuser=True,
            max_profile__max_alerts_enabled=True,
        )
        .exclude(max_profile__max_user_id="")
        .order_by("pk")
    )


def max_user_id_for(user: AbstractBaseUser) -> str:
    """Return trimmed MAX user id or empty string."""
    profile = getattr(user, "max_profile", None)
    if profile is None:
        return ""
    if not getattr(profile, "max_alerts_enabled", False):
        return ""
    return (getattr(profile, "max_user_id", "") or "").strip()


def send_max_to_users(users: QuerySet[Any] | list[Any], text: str) -> int:
    """Send plain text to each staff user's MAX dialog; return success count."""
    body = (text or "").strip()
    if not body:
        return 0
    sent = 0
    seen: set[str] = set()
    for user in users:
        uid = max_user_id_for(user)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        result: PublishResult = publish_max(user_id=uid, text=body)
        if result.ok:
            sent += 1
    return sent


def compose_staff_max_support_alert(
    conversation: Any,
    *,
    inbound_message_id: int | None = None,
) -> tuple[str, str]:
    """Title/body for MAX staff alert on inbound support message."""
    from sitesettings.staff_push import staff_support_push_copy
    from social.max_staff_reply import staff_reply_hint
    from supportchat.models import Message, MessageDirection

    label = conversation.display_name or conversation.get_channel_display()
    title, fallback_body = staff_support_push_copy(label=label)
    title = f"{title} · #{conversation.pk}"

    inbound: Message | None = None
    if inbound_message_id is not None:
        inbound = Message.objects.filter(
            pk=inbound_message_id,
            conversation_id=conversation.pk,
            direction=MessageDirection.INBOUND,
        ).first()
    if inbound is None:
        inbound = (
            Message.objects.filter(
                conversation_id=conversation.pk,
                direction=MessageDirection.INBOUND,
            )
            .order_by("-id")
            .first()
        )

    parts: list[str] = []
    if inbound is not None:
        snippet = (inbound.body or "").strip().replace("\n", " ")
        if len(snippet) > 400:
            snippet = snippet[:399].rstrip() + "…"
        if snippet:
            channel_label = conversation.get_channel_display()
            parts.append(f"{channel_label} · {label}:\n«{snippet}»")
    if not parts:
        parts.append(fallback_body)

    parts.append(staff_reply_hint(conversation.pk))
    return title, "\n\n".join(parts)


def format_staff_max_message(*, title: str, body: str, url: str = "") -> str:
    """Compose plain MAX staff alert with optional Admin deep link."""
    from django.conf import settings

    parts = [title, body]
    path = (url or "").strip()
    if path:
        site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
        if path.startswith("http"):
            link = path
        else:
            link = f"{site}{path if path.startswith('/') else '/' + path}"
        parts.append(f"Открыть в Admin: {link}")
    return "\n".join(parts)
