"""Yandex Mail compose links for manager replies."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from crm.mail_links import build_lead_reply_email_url, build_yandex_compose_url
from leads.models import Lead


def test_yandex_compose_url_uses_web_interface() -> None:
    """Compose opens mail.yandex.ru, not mailto."""
    url = build_yandex_compose_url(
        to="client@example.com",
        subject="КП #7 — ООО Ромашка",
        from_email="mgr@yandex.ru",
    )
    assert url.startswith("https://mail.yandex.ru/compose?")
    assert "to=client%40example.com" in url
    assert "from=mgr%40yandex.ru" in url
    assert "subject=" in url


def test_yandex_compose_com_host_for_yandex_com_mailbox() -> None:
    """@yandex.com mailboxes use mail.yandex.com compose."""
    url = build_yandex_compose_url(
        to="client@example.com",
        subject="Hi",
        from_email="mgr@yandex.com",
    )
    assert url.startswith("https://mail.yandex.com/compose?")


def test_build_lead_reply_email_url_wraps_compose() -> None:
    """Lead reply helper passes manager profile email as from."""
    url = build_lead_reply_email_url(
        lead_email="buyer@corp.ru",
        subject="КП #3 — Corp",
        manager_email="sales@hoocon.ru",
    )
    assert "buyer%40corp.ru" in url
    assert "from=sales%40hoocon.ru" in url


@pytest.mark.django_db
def test_lead_view_reply_button_opens_yandex_compose() -> None:
    """Кнопка «Ответить в Яндекс.Почте» на заявке — веб-compose с from менеджера."""
    user = get_user_model().objects.create_superuser(
        username="lead-mail-mgr",
        email="manager@yandex.ru",
        password="x",
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        company="ООО Тест",
        phone="+79001234567",
        message="Нужно КП",
    )
    client = Client()
    client.force_login(user)
    response = client.get(reverse("admin:leads_lead_change", args=[lead.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Ответить в Яндекс.Почте" in html
    assert "mail.yandex.ru/compose" in html
    assert "from=manager%40yandex.ru" in html
    assert "client%40example.com" in html
