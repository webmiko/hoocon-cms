"""Staff actions: VK assignee notifications."""

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


@pytest.mark.django_db
def test_notify_conversation_assigned_sends_vk_dm() -> None:
    actor = get_user_model().objects.create_user(
        username="actor-vk",
        email="actor-vk@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    target = get_user_model().objects.create_user(
        username="target-vk",
        email="target-vk@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    target.groups.add(group)
    StaffVkProfile.objects.create(
        user=target,
        vk_user_id="800800",
        vk_alerts_enabled=True,
    )
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="assign-vk")
    with patch(
        "social.publishers.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="99"),
    ) as vk_dm:
        notify_conversation_assigned(conv, target, actor)
    vk_dm.assert_called_once()


@pytest.mark.django_db
def test_notify_conversation_assigned_sends_telegram_and_max() -> None:
    """Assignee with Telegram + MAX profiles gets both DMs."""
    actor = get_user_model().objects.create_user(
        username="actor-mix",
        email="actor-mix@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    target = get_user_model().objects.create_user(
        username="target-mix",
        email="target-mix@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    target.groups.add(group)
    StaffTelegramProfile.objects.create(
        user=target,
        telegram_chat_id="8202",
        telegram_alerts_enabled=True,
    )
    StaffMaxProfile.objects.create(
        user=target,
        max_user_id="max-9",
        max_alerts_enabled=True,
    )
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
    ):
        notify_conversation_assigned(conv, target, actor)
    tg.assert_called_once()
    mx.assert_called_once()
