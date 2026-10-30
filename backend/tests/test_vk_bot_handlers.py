"""VK bot handlers: attachments and staff reply parsing."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.models import StaffVkProfile
from accounts.roles import GROUP_MANAGER
from social.vk_bot_handlers import try_staff_vk_reply, vk_message_attachment
from social.vk_staff_reply import staff_user_for_vk_user_id


def test_vk_message_attachment_downloads_doc() -> None:
    message = {
        "attachments": [
            {
                "type": "doc",
                "doc": {"url": "https://sun9-1.userapi.com/doc.pdf", "title": "spec.pdf", "ext": "pdf"},
            },
        ],
    }
    with patch(
        "social.vk_http.vk_download_attachment",
        return_value=(b"pdf", "spec.pdf"),
    ):
        got = vk_message_attachment(message)
    assert got is not None
    assert got[1] == "spec.pdf"


def test_vk_message_attachment_picks_largest_photo() -> None:
    message = {
        "attachments": [
            {
                "type": "photo",
                "photo": {
                    "sizes": [
                        {"url": "https://sun9-1.userapi.com/small.jpg", "width": 1, "height": 1},
                        {"url": "https://sun9-1.userapi.com/large.jpg", "width": 100, "height": 80},
                    ],
                },
            },
        ],
    }
    with patch(
        "social.vk_http.vk_download_attachment",
        return_value=(b"jpeg-bytes", "large.jpg"),
    ) as dl:
        got = vk_message_attachment(message)
    assert got is not None
    dl.assert_called_once_with("https://sun9-1.userapi.com/large.jpg")


@pytest.mark.django_db
def test_staff_user_for_vk_user_id_prefers_support_permission() -> None:
    user = get_user_model().objects.create_user(
        username="vk-mgr",
        email="vk-mgr@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffVkProfile.objects.create(user=user, vk_user_id="555001", vk_alerts_enabled=True)
    found = staff_user_for_vk_user_id("555001")
    assert found is not None
    assert found.pk == user.pk


@pytest.mark.django_db
def test_try_staff_vk_reply_parses_hash_command() -> None:
    from supportchat.models import Channel, Conversation

    user = get_user_model().objects.create_user(
        username="vk-reply",
        email="vk-reply@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffVkProfile.objects.create(user=user, vk_user_id="555002", vk_alerts_enabled=True)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="web-vk-reply")
    with patch(
        "social.vk_bot_handlers.submit_staff_reply_from_vk",
        return_value=(True, "ok"),
    ) as submit:
        with patch("social.vk_bot_handlers.send_to_vk_user") as send:
            try_staff_vk_reply("555002", f"#{conv.pk} Ответ клиенту")
    submit.assert_called_once()
    send.assert_called_once()


@pytest.mark.django_db
def test_handle_message_event_reply_sets_pending_mode() -> None:
    from social.max_staff_reply import staff_reply_callback_payload
    from social.vk_bot_handlers import handle_message_event
    from social.vk_staff_reply import get_pending_staff_reply
    from supportchat.models import Channel, Conversation

    user = get_user_model().objects.create_user(
        username="vk-ev",
        email="vk-ev@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffVkProfile.objects.create(user=user, vk_user_id="555003", vk_alerts_enabled=True)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="web-ev")
    event = {
        "object": {
            "user_id": 555003,
            "peer_id": 555003,
            "event_id": 1,
            "payload": staff_reply_callback_payload(conv.pk),
        },
    }
    with patch("social.vk_bot_handlers.answer_vk_message_event"):
        handle_message_event(event)
    assert get_pending_staff_reply("555003") == (conv.pk, "reply")
