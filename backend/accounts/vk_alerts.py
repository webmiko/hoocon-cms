"""Staff VK alert recipients and send helpers."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet

from accounts.roles import GROUP_MANAGER
from social.publishers import PublishResult, publish_vk_dm

User = get_user_model()


def staff_vk_recipients_managers(*, lead_assignee_id: int | None = None) -> QuerySet[Any]:
    base = (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            groups__name=GROUP_MANAGER,
            vk_profile__vk_alerts_enabled=True,
        )
        .exclude(vk_profile__vk_user_id="")
        .distinct()
    )
    if lead_assignee_id is not None:
        assigned = base.filter(pk=lead_assignee_id)
        if assigned.exists():
            return assigned
    return base.order_by("pk")


def staff_vk_recipients_superusers() -> QuerySet[Any]:
    return (
        User.objects.filter(
            is_active=True,
            is_superuser=True,
            vk_profile__vk_alerts_enabled=True,
        )
        .exclude(vk_profile__vk_user_id="")
        .order_by("pk")
    )


def vk_user_id_for(user: AbstractBaseUser) -> str:
    profile = getattr(user, "vk_profile", None)
    if profile is None:
        return ""
    if not getattr(profile, "vk_alerts_enabled", False):
        return ""
    return (getattr(profile, "vk_user_id", "") or "").strip()


def send_vk_to_users(
    users: QuerySet[Any] | list[Any],
    text: str,
    *,
    keyboard: str | None = None,
    cmids_out: dict[str, str] | None = None,
) -> int:
    body = (text or "").strip()
    if not body:
        return 0
    sent = 0
    seen: set[str] = set()
    for user in users:
        uid = vk_user_id_for(user)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        result: PublishResult = publish_vk_dm(user_id=uid, text=body, keyboard=keyboard)
        if result.ok:
            sent += 1
            if cmids_out is not None and result.external_id:
                cmids_out[uid] = result.external_id
    return sent


def format_staff_vk_message(*, title: str, body: str, url: str = "") -> str:
    from django.conf import settings

    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    lines = [title.strip(), "", body.strip()]
    if url:
        path = url if url.startswith("/") else f"/{url.lstrip('/')}"
        lines.extend(["", f"{site}{path}"])
    return "\n".join(lines).strip()
