"""Public support widget API tests."""

from __future__ import annotations

from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.test import Client, override_settings

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
    """Staff messenger shows «Пользователь» when inbound has no name."""
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from supportchat.models import Channel, Message, MessageDirection
    from supportchat.services import conversation_party_label, message_sender_name

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
    assert message_sender_name(msg, staff_view=True) == "Пользователь"
    assert conversation_party_label(conv) == "Пользователь"

    client = Client()
    client.force_login(staff)
    url = reverse("admin:supportchat_conversation_messages_poll", args=[conv.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["sender_name"] == "Пользователь"


@pytest.mark.django_db
def test_conversation_party_label_name_company_and_anonymous_phone() -> None:
    """Hub label prefers name·company; anonymous uses phone."""
    from crm.models import Client
    from leads.models import Lead
    from supportchat.models import Channel
    from supportchat.services import conversation_party_label

    named = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-named",
        display_name="",
        status="open",
    )
    named.client = Client.objects.create(
        name="Иван",
        email="ivan@example.com",
        company="ООО Ромашка",
        phone="+79001112233",
    )
    named.save(update_fields=["client"])
    assert conversation_party_label(named) == "Иван · ООО Ромашка"

    anon = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-phone",
        display_name="",
        status="open",
    )
    anon.lead = Lead.objects.create(
        name="",
        email="anon@example.com",
        phone="+79005556677",
        company="",
        message="",
    )
    anon.save(update_fields=["lead"])
    assert conversation_party_label(anon) == "Пользователь · +79005556677"


@pytest.mark.django_db
def test_conversation_party_phone_company_skip_empty_lead() -> None:
    """Empty client/lead fields fall through; only non-empty values are returned."""
    from crm.models import Client
    from leads.models import Lead
    from supportchat.models import Channel
    from supportchat.services import conversation_party_company, conversation_party_phone

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-empty-fields",
        status="open",
    )
    conv.client = Client.objects.create(
        name="X",
        email="empty-fields@example.com",
        company="",
        phone="",
    )
    conv.lead = Lead.objects.create(
        name="",
        email="empty-lead@example.com",
        phone="",
        company="",
        message="",
    )
    conv.save(update_fields=["client", "lead"])
    assert conversation_party_phone(conv) == ""
    assert conversation_party_company(conv) == ""

    conv.lead.phone = "+79009998877"
    conv.lead.company = "Лид Ко"
    conv.lead.save(update_fields=["phone", "company"])
    assert conversation_party_phone(conv) == "+79009998877"
    assert conversation_party_company(conv) == "Лид Ко"


@pytest.mark.django_db
def test_chat_messages_for_admin_select_related_party_no_n_plus_one() -> None:
    """Serializing N inbound messages must not lazy-load client/lead per row."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from crm.models import Client
    from supportchat.admin import _chat_messages_for_admin
    from supportchat.models import Channel, Message, MessageDirection

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-n1-admin",
        display_name="",
        status="open",
    )
    conv.client = Client.objects.create(
        name="Оля",
        email="olya@example.com",
        company="ООО Север",
        phone="+79001110000",
    )
    conv.save(update_fields=["client"])
    for i in range(2):
        Message.objects.create(
            conversation=conv,
            direction=MessageDirection.INBOUND,
            body=f"msg-{i}",
        )

    def party_fk_queries() -> tuple[int, int, list]:
        with CaptureQueriesContext(connection) as ctx:
            rows = _chat_messages_for_admin(conv)
        sqls = [q["sql"].lower() for q in ctx.captured_queries]
        # Separate SELECTs on party tables (JOIN in the messages query is OK).
        client_sel = sum(
            1 for s in sqls if "crm_client" in s and s.lstrip().startswith("select") and "supportchat_message" not in s
        )
        lead_sel = sum(
            1 for s in sqls if "leads_lead" in s and s.lstrip().startswith("select") and "supportchat_message" not in s
        )
        return client_sel, lead_sel, rows

    client_sel, lead_sel, rows = party_fk_queries()
    assert len(rows) == 2
    assert rows[0]["sender_name"] == "Оля"
    assert client_sel == 0
    assert lead_sel == 0

    for i in range(2, 8):
        Message.objects.create(
            conversation=conv,
            direction=MessageDirection.INBOUND,
            body=f"msg-{i}",
        )
    client_sel2, lead_sel2, rows2 = party_fk_queries()
    assert len(rows2) == 8
    assert client_sel2 == 0
    assert lead_sel2 == 0


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


@pytest.mark.django_db
@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    LEAD_NOTIFY_EMAIL="sales@hoocon.ru",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="https://hoocon.ru",
)
def test_first_inbound_sends_email_second_does_not(
    django_capture_on_commit_callbacks,
) -> None:
    """Only the first client message in a thread emails sales@."""
    from django.core import mail

    from supportchat.models import Channel
    from supportchat.services import add_inbound_message

    ensure_default_schedule()
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-email-first",
        display_name="Ирина",
    )
    mail.outbox.clear()
    with patch("supportchat.services.is_open_now", return_value=True):
        with django_capture_on_commit_callbacks(execute=True):
            add_inbound_message(conv, "Здравствуйте, нужен подбор привода")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["sales@hoocon.ru"]
    assert f"#{conv.pk}" in msg.subject
    assert "Ирина" in msg.subject
    assert "нужен подбор" in msg.body
    assert f"/admin/supportchat/conversation/{conv.pk}/change/" in msg.body

    mail.outbox.clear()
    with patch("supportchat.services.is_open_now", return_value=True):
        with django_capture_on_commit_callbacks(execute=True):
            add_inbound_message(conv, "ещё одно сообщение")
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    LEAD_NOTIFY_EMAIL="sales@hoocon.ru",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_first_inbound_email_goes_to_assignee(
    django_capture_on_commit_callbacks,
) -> None:
    """Claimed thread notifies the assignee email, not the sales list."""
    from django.contrib.auth import get_user_model
    from django.core import mail

    from supportchat.models import Channel
    from supportchat.services import add_inbound_message

    ensure_default_schedule()
    mgr = get_user_model().objects.create_user(
        username="mgr-chat@hoocon.ru",
        email="mgr-chat@hoocon.ru",
        password="password12",
        is_staff=True,
        is_active=True,
    )
    conv = Conversation.objects.create(
        channel=Channel.TELEGRAM,
        external_user_id="tg-42",
        display_name="Павел",
        assignee=mgr,
    )
    mail.outbox.clear()
    with patch("supportchat.services.is_open_now", return_value=True):
        with django_capture_on_commit_callbacks(execute=True):
            add_inbound_message(conv, "привет из бота")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["mgr-chat@hoocon.ru"]


@pytest.mark.django_db
@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    LEAD_NOTIFY_EMAIL="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_first_inbound_skips_email_without_recipients(
    django_capture_on_commit_callbacks,
) -> None:
    """No LEAD_NOTIFY_EMAIL and no assignee → no mail, chat still works."""
    from django.core import mail

    from supportchat.models import Channel, Message, MessageDirection
    from supportchat.services import add_inbound_message

    ensure_default_schedule()
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-no-mail",
        display_name="X",
    )
    mail.outbox.clear()
    with patch("supportchat.services.is_open_now", return_value=True):
        with django_capture_on_commit_callbacks(execute=True):
            add_inbound_message(conv, "есть кто?")
    assert mail.outbox == []
    assert (
        Message.objects.filter(
            conversation=conv,
            direction=MessageDirection.INBOUND,
        ).count()
        == 1
    )
