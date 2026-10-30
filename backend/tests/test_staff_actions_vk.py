"""Assign-dialog pings: VK / Telegram / MAX, and skip when alerts are off."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.models import StaffMaxProfile, StaffTelegramProfile, StaffVkProfile
from accounts.roles import GROUP_MANAGER
from social.publishers import PublishResult
from supportchat.models import Channel, Conversation
from supportchat.staff_actions import notify_conversation_assigned


def _manager(*, email: str) -> object:
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password="pw-12345",
        is_staff=True,
        first_name="Mgr",
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    return user


@pytest.mark.django_db
def test_notify_assigned_sends_vk_dm_with_reply_keyboard() -> None:
    """New assignee with VK alerts on gets a DM that names the dialog."""
    actor = _manager(email="actor-vk@hoocon.ru")
    target = _manager(email="target-vk@hoocon.ru")
    StaffVkProfile.objects.create(user=target, vk_user_id="800800", vk_alerts_enabled=True)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="assign-vk")
    with patch(
        "social.publishers.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="99"),
    ) as vk_dm:
        notify_conversation_assigned(conv, target, actor)
    kwargs = vk_dm.call_args.kwargs
    assert kwargs["user_id"] == "800800"
    assert f"#{conv.pk}" in kwargs["text"]
    assert "Ответить" in (kwargs.get("keyboard") or "")


@pytest.mark.django_db
def test_notify_assigned_skips_vk_when_alerts_disabled() -> None:
    """Alerts off on the VK profile → no community DM."""
    actor = _manager(email="actor-off@hoocon.ru")
    target = _manager(email="target-off@hoocon.ru")
    StaffVkProfile.objects.create(user=target, vk_user_id="800801", vk_alerts_enabled=False)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="assign-off")
    with patch("social.publishers.publish_vk_dm") as vk_dm:
        notify_conversation_assigned(conv, target, actor)
    assert not vk_dm.called


@pytest.mark.django_db
def test_notify_assigned_still_pings_telegram_and_max() -> None:
    """Telegram/MAX profiles stay independent of VK (regression: VK rewrite dropped TG)."""
    actor = _manager(email="actor-mix@hoocon.ru")
    target = _manager(email="target-mix@hoocon.ru")
    StaffTelegramProfile.objects.create(
        user=target,
        telegram_chat_id="8202",
        telegram_alerts_enabled=True,
    )
    StaffMaxProfile.objects.create(user=target, max_user_id="max-9", max_alerts_enabled=True)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="assign-mix")
    with (
        patch(
            "social.publishers.publish_telegram",
            return_value=PublishResult(ok=True, external_id="tg-1"),
        ) as tg,
        patch(
            "social.publishers.publish_max",
            return_value=PublishResult(ok=True, external_id="max-1"),
        ) as mx,
        patch("social.publishers.publish_vk_dm") as vk_dm,
    ):
        notify_conversation_assigned(conv, target, actor)
    assert tg.call_args.kwargs["chat_id"] == "8202"
    assert mx.call_args.kwargs["user_id"] == "max-9"
    assert not vk_dm.called
