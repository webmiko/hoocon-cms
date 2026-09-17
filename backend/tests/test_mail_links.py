"""Yandex Mail app-first compose links with web fallback."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from crm.mail_links import (
    build_lead_reply_email_urls,
    build_mailto_compose_url,
    build_yandex_compose_web_url,
    build_yandex_mail_android_intent_url,
    build_yandex_mail_app_url,
    format_lead_reply_body,
)
from leads.models import Lead, LeadItem

_BACKEND = Path(__file__).resolve().parents[1]
_MAIL_REPLY_JS = _BACKEND / "static/admin/js/hoocon-admin-lead-mail-reply.js"


def test_yandex_web_compose_url_uses_mailto_param_for_recipient() -> None:
    """Yandex web compose fills «Кому» via mailto=, not to=."""
    url = build_yandex_compose_web_url(
        to="client@example.com",
        subject="КП #7 — ООО Ромашка",
        body="Комментарий клиента",
        from_email="mgr@yandex.ru",
    )
    assert url.startswith("https://mail.yandex.ru/compose?")
    assert "mailto=client%40example.com" in url
    assert "&to=" not in url
    assert "?to=" not in url
    assert "from=mgr%40yandex.ru" in url
    assert "body=" in url


def test_yandex_web_compose_com_host_for_yandex_com_mailbox() -> None:
    """@yandex.com mailboxes use mail.yandex.com compose."""
    url = build_yandex_compose_web_url(
        to="client@example.com",
        subject="Hi",
        from_email="mgr@yandex.com",
    )
    assert url.startswith("https://mail.yandex.com/compose?")


def test_yandex_mail_app_url_uses_custom_scheme() -> None:
    """Native app deep link targets yandexmail:// compose."""
    url = build_yandex_mail_app_url(
        to="client@example.com",
        subject="КП #3",
        manager_email="mgr@yandex.ru",
        body="Позиции по заявке:\n- DA-01 × 2",
    )
    assert url.startswith("yandexmail://compose?")
    assert "to=client%40example.com" in url
    assert "body=" in url


def test_android_intent_targets_yandex_mail_package() -> None:
    """Android intent opens ru.yandex.mail instead of the browser."""
    mailto = build_mailto_compose_url(
        to="buyer@corp.ru",
        subject="КП",
        body="Нужны приводы",
    )
    intent = build_yandex_mail_android_intent_url(mailto)
    assert intent.startswith("intent:mailto:")
    assert "package=ru.yandex.mail" in intent


@pytest.mark.django_db
def test_format_lead_reply_body_includes_message_and_skus() -> None:
    """Reply body carries client comment and SKU lines for the KP."""
    lead = Lead.objects.create(
        name="Клиент",
        email="client@example.com",
        company="ООО Тест",
        message="Нужно коммерческое предложение до пятницы.",
    )
    LeadItem.objects.create(lead=lead, sku_code="DA-24V-05", quantity=3)
    LeadItem.objects.create(lead=lead, sku_code="SA-230V-10", quantity=1)

    body = format_lead_reply_body(lead)
    assert "Нужно коммерческое предложение до пятницы." in body
    assert "Позиции по заявке:" in body
    assert "- DA-24V-05 × 3" in body
    assert "- SA-230V-10 × 1" in body


def test_build_lead_reply_email_urls_bundle() -> None:
    """Lead reply helper returns web + native links."""
    urls = build_lead_reply_email_urls(
        lead_email="buyer@corp.ru",
        subject="КП #3 — Corp",
        manager_email="sales@hoocon.ru",
        body="Комментарий\n\nПозиции по заявке:\n- DA-01 × 2",
    )
    assert urls.web.startswith("https://mail.yandex.ru/compose")
    assert "mailto=buyer%40corp.ru" in urls.web
    assert "body=" in urls.web
    assert urls.yandex_app.startswith("yandexmail://")
    assert "ru.yandex.mail" in urls.yandex_android
    assert urls.mailto.startswith("mailto:")


def test_lead_mail_reply_js_falls_back_to_web() -> None:
    """Loaded JS tries native app, then opens web compose on timeout."""
    js = _MAIL_REPLY_JS.read_text(encoding="utf-8")
    assert "tryNativeThenWeb" in js
    assert "visibilitychange" in js
    assert "window.open" in js


@pytest.mark.django_db
def test_lead_view_reply_button_prefills_recipient_and_body() -> None:
    """Кнопка ответа подставляет mailto= клиента и текст заявки с артикулами."""
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
        message="Просьба прислать КП",
    )
    LeadItem.objects.create(lead=lead, sku_code="HV-100", quantity=2)
    client = Client()
    client.force_login(user)
    response = client.get(reverse("admin:leads_lead_change", args=[lead.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Ответить в Яндекс.Почте" in html
    assert "mailto=client%40example.com" in html
    assert "Просьба%20прислать%20%D0%9A%D0%9F" in html or "body=" in html
    assert "HV-100" in html
    assert "from=manager%40yandex.ru" in html
