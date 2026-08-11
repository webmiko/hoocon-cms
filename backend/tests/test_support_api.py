"""Public support widget API tests."""

from __future__ import annotations

from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from supportchat.models import Conversation
from supportchat.schedule import ensure_default_schedule

MSK = ZoneInfo("Europe/Moscow")


def _csrf_client() -> Client:
    client = Client(enforce_csrf_checks=True)
    client.get("/api/csrf/")
    return client


@pytest.mark.django_db
def test_schedule_endpoint_public() -> None:
    ensure_default_schedule()
    client = Client()
    resp = client.get("/api/support/schedule/")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_open_now" in data
    assert data["timezone"] == "Europe/Moscow"
    assert len(data["days"]) == 7


@pytest.mark.django_db
def test_channels_hides_tokens(settings) -> None:
    settings.TELEGRAM_BOT_USERNAME = "hoocon_bot"
    settings.TELEGRAM_CHANNEL_USERNAME = "hoocon_moscow"
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_enabled = True
    site.telegram_bot_token = "secret-token-value"
    site.save()
    client = Client()
    resp = client.get("/api/support/channels/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "secret-token-value" not in body
    channels = resp.json()["channels"]
    assert channels == [
        {
            "channel": "telegram_bot",
            "label": "Написать в Telegram",
            "deep_link": "https://t.me/hoocon_bot?start=support",
        },
        {
            "channel": "telegram_channel",
            "label": "Канал Telegram",
            "deep_link": "https://t.me/hoocon_moscow",
        },
    ]


@pytest.mark.django_db
def test_web_message_roundtrip_and_idor() -> None:
    ensure_default_schedule()
    with patch("supportchat.services.is_open_now", return_value=True):
        c1 = _csrf_client()
        token = c1.cookies["csrftoken"].value
        start = c1.post(
            "/api/support/conversations/",
            data={"display_name": "Ivan"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert start.status_code == 201
        assert start.json()["id"] is not None
        assert start.json()["display_name"] == "Ivan"

        send = c1.post(
            "/api/support/conversations/current/messages/",
            data={"body": "Нужен КП"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert send.status_code == 201
        assert send.json()["message"]["body"] == "Нужен КП"
        assert send.json()["message"]["sender_name"] == "Ivan"

        listing = c1.get("/api/support/conversations/current/messages/")
        assert listing.status_code == 200
        assert len(listing.json()["messages"]) >= 1
        assert listing.json()["messages"][0]["sender_name"] == "Ivan"

    # Other session cannot see messages (empty own thread).
    c2 = Client()
    other = c2.get("/api/support/conversations/current/messages/")
    assert other.status_code == 200
    assert other.json()["messages"] == []


@pytest.mark.django_db
def test_outside_hours_auto_reply() -> None:
    ensure_default_schedule()
    with patch("supportchat.services.is_open_now", return_value=False):
        client = _csrf_client()
        token = client.cookies["csrftoken"].value
        client.post(
            "/api/support/conversations/",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        send = client.post(
            "/api/support/conversations/current/messages/",
            data={"body": "Поздно пишу"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert send.status_code == 201
        assert "auto_reply" in send.json()
        assert send.json()["message"]["outside_hours"] is True


@pytest.mark.django_db
def test_staff_outbound_visible_on_poll_after() -> None:
    """Visitor poll with ?after= must return Admin outbound replies."""
    ensure_default_schedule()
    from django.contrib.auth import get_user_model

    from supportchat.models import Message, MessageDirection
    from supportchat.services import add_staff_reply

    staff = get_user_model().objects.create_user(
        username="agent",
        password="x",
        first_name="Анна",
    )

    with patch("supportchat.services.is_open_now", return_value=True):
        client = _csrf_client()
        token = client.cookies["csrftoken"].value
        client.post(
            "/api/support/conversations/",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        send = client.post(
            "/api/support/conversations/current/messages/",
            data={"body": "Вопрос"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert send.status_code == 201
        inbound_id = send.json()["message"]["id"]

        conv = Conversation.objects.get()
        with patch("webpush.tasks.notify_visitor_support_reply.delay"):
            outbound = add_staff_reply(conv, "Ответ менеджера", author=staff)
        assert outbound.direction == MessageDirection.OUTBOUND
        conv.refresh_from_db()
        assert conv.assignee_id == staff.pk

        polled = client.get(
            f"/api/support/conversations/current/messages/?after={inbound_id}",
        )
        assert polled.status_code == 200
        bodies = [m["body"] for m in polled.json()["messages"]]
        assert "Ответ менеджера" in bodies
        assert polled.json()["messages"][0]["sender_name"] == "Анна"
        assert Message.objects.filter(direction=MessageDirection.OUTBOUND).count() == 1


@pytest.mark.django_db
def test_support_poll_throttle_scope_allows_burst() -> None:
    """GET poll must not share the tight POST support_message budget."""
    ensure_default_schedule()
    client = _csrf_client()
    token = client.cookies["csrftoken"].value
    client.post(
        "/api/support/conversations/",
        data={},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    # More GETs than the old shared 30/hour POST budget.
    statuses = [client.get("/api/support/conversations/current/messages/").status_code for _ in range(40)]
    assert all(code == 200 for code in statuses)


@pytest.mark.django_db
def test_admin_reply_view_creates_outbound_and_enqueues_deliver() -> None:
    """Admin «Отправить» must hit reply/ (not change/) and enqueue Celery."""
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from supportchat.models import Channel, Message, MessageDirection

    ensure_default_schedule()
    staff = get_user_model().objects.create_superuser(
        username="support-admin",
        email="support-admin@example.com",
        password="x",
    )
    conv = Conversation.objects.create(
        channel=Channel.TELEGRAM,
        external_user_id="1850806353",
        display_name="TG test",
        status="open",
    )
    client = Client()
    client.force_login(staff)
    url = reverse("admin:supportchat_conversation_reply", args=[conv.pk])
    with patch("supportchat.tasks.deliver_outbound_message.delay") as delay:
        resp = client.post(url, data={"reply_body": "Ответ из админки"})
    assert resp.status_code == 302
    out = Message.objects.filter(conversation=conv, direction=MessageDirection.OUTBOUND)
    assert out.count() == 1
    assert out.get().body == "Ответ из админки"
    delay.assert_called_once_with(out.get().pk)


@pytest.mark.django_db
def test_admin_reply_form_is_outside_main_change_form() -> None:
    """Reply form must render in Unfold form_before (not nested in change form)."""
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from supportchat.models import Channel

    staff = get_user_model().objects.create_superuser(
        username="support-admin2",
        email="support-admin2@example.com",
        password="x",
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="session-uuid-test",
        display_name="Web test",
        status="open",
    )
    client = Client()
    client.force_login(staff)
    page = client.get(reverse("admin:supportchat_conversation_change", args=[conv.pk]))
    assert page.status_code == 200
    html = page.content.decode()
    assert 'name="reply_body"' in html
    assert 'id="hoocon-messenger"' in html
    assert "hoocon-messenger__send" in html
    assert f"/admin/supportchat/conversation/{conv.pk}/reply/" in html
    assert "hoocon-support-messenger.js" in html
    assert "data-poll-url" in html
    assert f"/admin/supportchat/conversation/{conv.pk}/messages/" in html


@pytest.mark.django_db
def test_admin_messages_poll_returns_new_inbound() -> None:
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from supportchat.models import Channel, Message, MessageDirection

    staff = get_user_model().objects.create_superuser(
        username="support-poll",
        email="support-poll@example.com",
        password="x",
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="session-poll",
        display_name="Poll test",
        status="open",
        staff_unread_count=1,
    )
    first = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Первое",
    )
    second = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Второе без F5",
    )
    client = Client()
    client.force_login(staff)
    url = reverse("admin:supportchat_conversation_messages_poll", args=[conv.pk])
    resp = client.get(url, {"after": first.pk})
    assert resp.status_code == 200
    assert "no-store" in resp["Cache-Control"]
    payload = resp.json()["messages"]
    assert len(payload) == 1
    assert payload[0]["id"] == second.pk
    assert payload[0]["body"] == "Второе без F5"
    assert payload[0]["direction"] == MessageDirection.INBOUND
    conv.refresh_from_db()
    # Poll is read-only — unread clears only on change_view / mark-read action.
    assert conv.staff_unread_count == 1


@pytest.mark.django_db
def test_admin_poll_sender_name_for_anonymous_inbound() -> None:
    """Staff messenger shows «Клиент» when inbound has no display_name."""
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from supportchat.models import Channel, Message, MessageDirection
    from supportchat.services import message_sender_name

    staff = get_user_model().objects.create_superuser(
        username="support-name",
        email="support-name@example.com",
        password="x",
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="session-anon",
        display_name="",
        status="open",
    )
    msg = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="hi",
    )
    assert message_sender_name(msg) == "Вы"
    assert message_sender_name(msg, staff_view=True) == "Клиент"

    client = Client()
    client.force_login(staff)
    url = reverse("admin:supportchat_conversation_messages_poll", args=[conv.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["sender_name"] == "Клиент"


@pytest.mark.django_db
def test_touch_conversation_message_bumps_unread_atomically() -> None:
    """Concurrent inbound bumps must not lose counts (F() expression)."""
    from supportchat.models import Channel, touch_conversation_message

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="session-unread",
        display_name="U",
        status="open",
        staff_unread_count=0,
    )
    touch_conversation_message(conv, inbound=True)
    touch_conversation_message(conv, inbound=True)
    conv.refresh_from_db()
    assert conv.staff_unread_count == 2


@pytest.mark.django_db
def test_inbound_reopens_closed_web_conversation() -> None:
    ensure_default_schedule()
    from supportchat.models import Channel, ConversationStatus
    from supportchat.services import add_inbound_message

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-closed",
        display_name="C",
        status=ConversationStatus.CLOSED,
        staff_unread_count=0,
    )
    with patch("supportchat.services.is_open_now", return_value=True):
        add_inbound_message(conv, "снова пишу")
    conv.refresh_from_db()
    assert conv.status == ConversationStatus.OPEN
    assert conv.staff_unread_count == 1


@pytest.mark.django_db
def test_outside_hours_auto_reply_once_per_day() -> None:
    ensure_default_schedule()
    from supportchat.models import Channel, Message, MessageDirection
    from supportchat.services import add_inbound_message

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-auto",
        display_name="A",
    )
    with patch("supportchat.services.is_open_now", return_value=False):
        _in1, auto1 = add_inbound_message(conv, "первый")
        _in2, auto2 = add_inbound_message(conv, "второй")
    assert auto1 is not None
    assert auto2 is None
    assert (
        Message.objects.filter(
            conversation=conv,
            direction=MessageDirection.SYSTEM,
            outside_hours=True,
        ).count()
        == 1
    )
