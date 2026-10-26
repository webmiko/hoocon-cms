"""Client quote links: the email names the manager; accept and revise do not need a cabinet."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from crm.models import Activity, Client, Quote, QuoteStatus

User = get_user_model()


def _issued_quote() -> tuple[Client, Quote, object]:
    manager = User.objects.create_user(
        username="anna@hoocon.test",
        email="anna@hoocon.test",
        first_name="",
        is_staff=True,
    )
    client = Client.objects.create(name="Покупатель", email="buyer@acme.test", company="Акме")
    quote = Quote.objects.create(
        client=client,
        created_by=manager,
        status=QuoteStatus.SENT,
        valid_until=timezone.localdate() + timedelta(days=10),
    )
    quote.refresh_from_db()
    return client, quote, manager


@pytest.mark.django_db
def test_quote_email_names_manager_deadline_and_reply_links(settings) -> None:
    """Письмо КП: менеджер, срок и две ссылки. Вход в кабинет не предлагается."""
    settings.SITE_URL = "https://hoocon.test"
    settings.MANAGER_SIGNATURE_CONTACTS = {
        "anna@hoocon.test": {"name": "Анна Смирнова", "phone": "+7 495 000-00-00", "company": "Hoocon"},
    }
    _client, quote, _manager = _issued_quote()
    from crm.email_body import is_html_email_body
    from crm.quote_docs import notify_quote_issued, render_quote_issued_email

    _subject, text_body, html_body = render_quote_issued_email(quote, author=_manager)
    assert "Анна Смирнова" in text_body
    assert "+7 495 000-00-00" in text_body
    assert "anna@hoocon.test" in text_body
    assert f"Действует до {quote.valid_until:%d.%m.%Y}." in text_body
    assert "Согласовать: https://hoocon.test/kp#" in text_body
    assert "https://hoocon.test/kp?" not in text_body
    assert "action=accept" in text_body
    assert "Нужны правки: https://hoocon.test/kp#" in text_body
    assert "action=revise" in text_body
    assert "без входа в кабинет" in text_body
    assert "одноразовый код" not in text_body

    message = notify_quote_issued(quote, send_now=False, author=_manager)
    assert is_html_email_body(message.body)
    assert message.body == html_body
    assert "HOOCON" in message.body
    assert 'href="' in message.body and "action=accept" in message.body
    assert message.reply_to_email == "anna@hoocon.test"
    assert message.quote_id == quote.pk
    assert message.created_by_id == _manager.pk


@pytest.mark.django_db
def test_quote_issued_email_bccs_manager_via_shared_smtp(settings) -> None:
    """КП через общий SMTP → BCC менеджеру, тред в его ящике."""
    from django.core import mail as dj_mail

    from crm.quote_docs import QUOTE_ISSUED_SUBJECT_MARKER, notify_quote_issued
    from crm.tasks import send_crm_email

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@hoocon.ru"
    settings.SITE_URL = "https://hoocon.test"
    settings.MANAGER_SIGNATURE_CONTACTS = {
        "anna@hoocon.test": {"name": "Анна", "phone": "+7 495 000-00-00", "company": "Hoocon"},
    }
    _client, quote, manager = _issued_quote()
    msg = notify_quote_issued(quote, send_now=False, author=manager)
    assert QUOTE_ISSUED_SUBJECT_MARKER in msg.subject

    send_crm_email.run(msg.pk)

    assert len(dj_mail.outbox) == 1
    sent = dj_mail.outbox[0]
    assert sent.to == [_client.email]
    assert sent.reply_to == ["anna@hoocon.test"]
    assert sent.bcc == ["anna@hoocon.test"]


@pytest.mark.django_db
def test_quote_issued_from_personal_mailbox_still_bccs_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """КП с личного SMTP менеджера → BCC себе, чтобы копия была не только в «Отправленных»."""
    from accounts.models import StaffMailbox
    from crm.quote_docs import notify_quote_issued
    from crm.tasks import send_crm_email
    from tests.test_crm_imap_fetch import _FakeConnection

    _client, quote, manager = _issued_quote()
    StaffMailbox.objects.create(
        user=manager,
        imap_user="anna@hoocon.test",
        imap_password="x-not-secret",
        smtp_host="smtp.test",
        smtp_port=587,
        smtp_use_ssl=False,
    )
    msg = notify_quote_issued(quote, send_now=False, author=manager)
    conn = _FakeConnection()
    monkeypatch.setattr("crm.tasks.get_connection", lambda **kw: conn)

    send_crm_email.run(msg.pk)

    assert len(conn.sent) == 1
    sent = conn.sent[0]
    assert sent.from_email == "anna@hoocon.test"
    assert sent.bcc == ["anna@hoocon.test"]


@pytest.mark.django_db
def test_accept_link_is_once_and_a_bad_token_changes_nothing(settings) -> None:
    """Согласование один раз шлёт письмо менеджеру. Чужой и пустой токен — 404, статус на месте."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    _client, quote, _manager = _issued_quote()
    from crm.quote_reply import sign_quote_token

    token = sign_quote_token(quote.pk)
    api = APIClient()
    with patch("crm.tasks.send_mail") as mail:
        first = api.post("/api/quotes/reply/", {"token": token, "action": "accept"}, format="json")
        assert first.status_code == 200
        assert first.json()["status"] == QuoteStatus.ACCEPTED
        second = api.post("/api/quotes/reply/", {"token": token, "action": "accept"}, format="json")
        assert second.status_code == 200
        mail.assert_called_once()
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.ACCEPTED
    assert Activity.objects.filter(client_id=quote.client_id, subject__contains="согласовал").count() == 1

    missed = api.post("/api/quotes/reply/", {"token": "nope", "action": "accept"}, format="json")
    assert missed.status_code == 404
    assert api.get("/api/quotes/reply/", {"token": "nope"}).status_code == 404
    assert api.get("/api/quotes/reply/", HTTP_X_QUOTE_TOKEN="nope").status_code == 404
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.ACCEPTED


@pytest.mark.django_db
def test_expired_and_draft_links_do_not_accept() -> None:
    """Просроченное КП и черновик ссылкой не согласуются."""
    _client, quote, _manager = _issued_quote()
    from crm.quote_reply import sign_quote_token

    quote.valid_until = timezone.localdate() - timedelta(days=1)
    quote.save(update_fields=["valid_until"])
    api = APIClient()
    refused = api.post(
        "/api/quotes/reply/",
        {"token": sign_quote_token(quote.pk), "action": "accept"},
        format="json",
    )
    assert refused.status_code == 400
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.SENT

    draft = Quote.objects.create(client=quote.client, status=QuoteStatus.DRAFT, created_by=quote.created_by)
    assert api.get("/api/quotes/reply/", {"token": sign_quote_token(draft.pk)}).status_code == 404
    draft.refresh_from_db()
    assert draft.status == QuoteStatus.DRAFT


@pytest.mark.django_db
def test_revise_keeps_status_and_rejects_an_empty_comment(settings) -> None:
    """Правки пишутся в ленту и не переводят КП. Пустой комментарий не принимается."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    _client, quote, _manager = _issued_quote()
    from crm.quote_reply import sign_quote_token

    token = sign_quote_token(quote.pk)
    api = APIClient()
    empty = api.post("/api/quotes/reply/", {"token": token, "action": "revise", "comment": "  "}, format="json")
    assert empty.status_code == 400
    assert Activity.objects.count() == 0

    with patch("crm.tasks.send_mail") as mail:
        sent = api.post(
            "/api/quotes/reply/",
            {"token": token, "action": "revise", "comment": "Нужен привод на 10 Н·м"},
            format="json",
        )
    assert sent.status_code == 200
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.SENT
    note = Activity.objects.get()
    assert note.body == "Нужен привод на 10 Н·м"
    assert "правки" in note.subject
    mail.assert_called_once()

    unknown = api.post("/api/quotes/reply/", {"token": token, "action": "delete"}, format="json")
    assert unknown.status_code == 400
    assert api.post("/api/quotes/reply/", ["accept"], format="json").status_code == 400
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.SENT


@pytest.mark.django_db
def test_closed_quote_rejects_accept_and_a_long_comment() -> None:
    """Отклонённое КП нельзя согласовать. Комментарий длиннее 2000 знаков не пишется в ленту."""
    _client, quote, _manager = _issued_quote()
    from crm.quote_reply import sign_quote_token

    quote.status = QuoteStatus.REJECTED
    quote.save(update_fields=["status"])
    token = sign_quote_token(quote.pk)
    api = APIClient()
    assert api.post("/api/quotes/reply/", {"token": token, "action": "accept"}, format="json").status_code == 400
    assert (
        api.post(
            "/api/quotes/reply/",
            {"token": token, "action": "revise", "comment": "Нужна другая модель"},
            format="json",
        ).status_code
        == 400
    )
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.REJECTED
    assert Activity.objects.count() == 0

    quote.status = QuoteStatus.SENT
    quote.save(update_fields=["status"])
    huge = api.post(
        "/api/quotes/reply/",
        {"token": token, "action": "revise", "comment": "а" * 2001},
        format="json",
    )
    assert huge.status_code == 400
    assert Activity.objects.count() == 0


@pytest.mark.django_db
def test_accept_survives_a_missing_manager_and_a_dead_mail_queue() -> None:
    """Нет адреса менеджера или брокер лежит — КП всё равно согласовано. Сбой SMTP не роняет задачу."""
    from crm.quote_reply import sign_quote_token
    from crm.tasks import send_quote_reply_mail

    client = Client.objects.create(name="Покупатель", email="nomgr@acme.test", company="Акме")
    quiet_quote = Quote.objects.create(
        client=client,
        status=QuoteStatus.SENT,
        valid_until=timezone.localdate(),
    )
    api = APIClient()
    with patch("crm.tasks.send_quote_reply_mail.delay") as queued:
        quiet = api.post(
            "/api/quotes/reply/",
            {"token": sign_quote_token(quiet_quote.pk), "action": "accept"},
            format="json",
        )
    assert quiet.status_code == 200
    queued.assert_not_called()
    quiet_quote.refresh_from_db()
    assert quiet_quote.status == QuoteStatus.ACCEPTED

    _client, quote, _manager = _issued_quote()
    with patch("crm.tasks.send_quote_reply_mail.delay", side_effect=ConnectionError("broker down")):
        survived = api.post(
            "/api/quotes/reply/",
            {"token": sign_quote_token(quote.pk), "action": "accept"},
            format="json",
        )
    assert survived.status_code == 200
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.ACCEPTED
    assert Activity.objects.filter(client=quote.client, subject__contains="согласовал").count() == 1

    with patch("crm.tasks.send_mail", side_effect=OSError("smtp down")), pytest.raises(OSError, match="smtp down"):
        send_quote_reply_mail("Тема", "Текст", "anna@hoocon.test")
