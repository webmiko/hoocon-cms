"""Lead Admin: compose and send KP reply with manager Reply-To."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from crm.models import Client as CrmClient
from crm.models import EmailMessage, EmailStatus
from crm.services import create_lead_reply_email
from leads.models import Lead, LeadItem


@pytest.mark.django_db
def test_lead_change_shows_compose_reply_button(django_user_model) -> None:
    """Lead view mode links to in-admin compose instead of external mailto."""
    user = django_user_model.objects.create_superuser(
        username="lead-compose-btn",
        email="mgr@hoocon.ru",
        password="x",
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        company="ООО Тест",
        message="Нужно КП",
    )
    client = Client()
    client.force_login(user)
    response = client.get(reverse("admin:leads_lead_change", args=[lead.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Ответить клиенту" in html
    assert reverse("admin:leads_lead_compose_reply", args=[lead.pk]) in html
    assert "data-mailto-url" not in html


@pytest.mark.django_db
def test_lead_item_inline_add_button_uses_natural_russian_label(django_user_model) -> None:
    """Lead line inline add-row copy uses natural Russian, not Django add-another."""
    user = django_user_model.objects.create_superuser(
        username="lead-inline-add",
        email="mgr@hoocon.ru",
        password="x",
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        company="ООО Тест",
        message="Нужно КП",
    )
    client = Client()
    client.force_login(user)
    response = client.get(reverse("admin:leads_lead_change", args=[lead.pk]) + "?edit=1")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Добавить ещё одну позицию к заявке" in html
    assert "один Позиция заявки" not in html


@pytest.mark.django_db
def test_lead_compose_reply_form_prefills_fields(django_user_model) -> None:
    """Compose form prefills client email, subject and SKU body."""
    user = django_user_model.objects.create_superuser(
        username="lead-compose-form",
        email="mgr@hoocon.ru",
        password="x",
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        company="ООО Тест",
        message="Просьба прислать КП",
    )
    LeadItem.objects.create(lead=lead, sku_code="HV-100", quantity=2)
    client = Client()
    client.force_login(user)
    url = reverse("admin:leads_lead_compose_reply", args=[lead.pk])
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "client@example.com" in html
    assert f"КП #{lead.pk} — ООО Тест" in html
    assert "Просьба прислать КП" in html
    assert "HV-100" in html
    assert "mgr@hoocon.ru" in html
    assert "hoocon-mail-compose" in html
    assert 'data-format="bold"' in html
    assert "hoocon-mail-compose.css" in html
    assert "hoocon-mail-compose.js" in html
    assert "hoocon-mail-compose__send" in html
    assert "hoocon-mail-compose__actions" in html


@pytest.mark.django_db(transaction=True)
def test_lead_compose_reply_post_queues_email_with_reply_to(
    django_user_model,
    settings,
) -> None:
    """POST compose-reply creates CRM email with Reply-To and lead link."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.DEFAULT_FROM_EMAIL = "noreply@hoocon.ru"
    user = django_user_model.objects.create_superuser(
        username="lead-compose-send",
        email="ivan@hoocon.ru",
        password="x",
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        company="ООО Тест",
        message="Комментарий",
    )
    client = Client()
    client.force_login(user)
    url = reverse("admin:leads_lead_compose_reply", args=[lead.pk])
    change_url = reverse("admin:leads_lead_change", args=[lead.pk])

    with patch("crm.tasks.send_crm_email.delay") as delay_mock:
        response = client.post(
            url,
            {
                "to_email": "client@example.com",
                "subject": f"КП #{lead.pk} — ООО Тест",
                "body": "Добрый день, направляем КП.",
                "send_now": "on",
            },
        )

    assert response.status_code == 302
    assert response.url == change_url
    crm_client = CrmClient.objects.get(email="client@example.com")
    msg = EmailMessage.objects.get(client=crm_client, lead=lead)
    assert msg.status == EmailStatus.QUEUED
    assert msg.reply_to_email == "ivan@hoocon.ru"
    assert msg.to_email == "client@example.com"
    assert "ivan@hoocon.ru" in msg.body
    assert "Добрый день, направляем КП." in msg.body
    delay_mock.assert_called_once_with(msg.pk)


@pytest.mark.django_db
def test_send_crm_email_sends_html_multipart(settings) -> None:
    """Rich-text compose stores HTML and SMTP sends multipart/alternative."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@hoocon.ru"
    crm_client = CrmClient.objects.create(name="Buyer", email="buyer@example.com")
    msg = EmailMessage.objects.create(
        client=crm_client,
        to_email="buyer@example.com",
        from_email="noreply@hoocon.ru",
        subject="КП",
        body="<p><strong>Добрый день</strong></p>",
        status=EmailStatus.QUEUED,
    )

    from crm.tasks import send_crm_email

    send_crm_email(msg.pk)
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.body == "Добрый день"
    assert len(sent.alternatives) == 1
    assert sent.alternatives[0][0] == "<p><strong>Добрый день</strong></p>"
    assert sent.alternatives[0][1] == "text/html"


@pytest.mark.django_db
def test_send_crm_email_sets_reply_to_header(settings) -> None:
    """SMTP send includes Reply-To from EmailMessage.reply_to_email."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@hoocon.ru"
    crm_client = CrmClient.objects.create(name="Buyer", email="buyer@example.com")
    msg = EmailMessage.objects.create(
        client=crm_client,
        to_email="buyer@example.com",
        from_email="noreply@hoocon.ru",
        reply_to_email="mgr@hoocon.ru",
        subject="КП",
        body="Текст",
        status=EmailStatus.QUEUED,
    )

    from crm.tasks import send_crm_email

    send_crm_email(msg.pk)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].reply_to == ["mgr@hoocon.ru"]
    assert mail.outbox[0].bcc == []


@pytest.mark.django_db
def test_send_crm_email_bccs_manager_for_lead_reply(settings) -> None:
    """Lead compose reply BCCs manager mailbox so the thread is in their inbox."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@hoocon.ru"
    lead = Lead.objects.create(
        name="Клиент",
        email="bcc-client@example.com",
        company="ООО Тест",
    )
    crm_client = CrmClient.objects.get(email="bcc-client@example.com")
    msg = EmailMessage.objects.create(
        client=crm_client,
        lead=lead,
        to_email="bcc-client@example.com",
        from_email="noreply@hoocon.ru",
        reply_to_email="mgr@hoocon.ru",
        subject="КП",
        body="Текст",
        status=EmailStatus.QUEUED,
    )

    from crm.tasks import send_crm_email

    send_crm_email(msg.pk)
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == ["bcc-client@example.com"]
    assert sent.reply_to == ["mgr@hoocon.ru"]
    assert sent.bcc == ["mgr@hoocon.ru"]


@pytest.mark.django_db(transaction=True)
def test_lead_reply_includes_ludmila_signature_for_assistant_email(
    django_user_model,
    settings,
) -> None:
    """assistant@hoocon.ru replies append Ludmila signature before Reply-To hint."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    user = django_user_model.objects.create_user(
        username="ludmila",
        email="assistant@hoocon.ru",
        is_staff=True,
        first_name="Людмила",
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        company="ООО Атерна",
    )
    with patch("crm.tasks.send_crm_email.delay"):
        msg = create_lead_reply_email(
            lead=lead,
            subject="КП #1",
            body="Добрый день!",
            author=user,
            reply_to_email="assistant@hoocon.ru",
            send_now=True,
        )
    assert "С уважением, Людмила" in msg.body
    assert 'ООО "ХОГОН"' in msg.body
    assert "+7(995)780-70-18" in msg.body
    assert "assistant@hoocon.ru" in msg.body
    assert "Ответьте на это письмо" in msg.body


@pytest.mark.django_db(transaction=True)
def test_create_lead_reply_email_links_client_and_lead(
    django_user_model,
    settings,
) -> None:
    """Service helper creates CRM client from lead and stores lead FK."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    user = django_user_model.objects.create_user(
        username="lead-svc",
        email="svc@hoocon.ru",
        is_staff=True,
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="unique@example.com",
        company="Co",
    )
    with patch("crm.tasks.send_crm_email.delay"):
        msg = create_lead_reply_email(
            lead=lead,
            subject="КП #1",
            body="Текст менеджера",
            author=user,
            reply_to_email="svc@hoocon.ru",
            send_now=True,
        )
    assert msg.lead_id == lead.pk
    assert msg.client.email == "unique@example.com"
    assert msg.reply_to_email == "svc@hoocon.ru"
