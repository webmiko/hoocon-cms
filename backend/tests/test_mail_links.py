"""Yandex Mail app-first compose links with web fallback."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import pytest

from crm.mail_links import (
    build_lead_reply_email_urls,
    build_mailto_compose_url,
    build_yandex_compose_web_url,
    build_yandex_mail_android_intent_url,
    format_lead_reply_body,
)
from leads.models import Lead, LeadItem

_BACKEND = Path(__file__).resolve().parents[1]
_MAIL_REPLY_JS = _BACKEND / "static/admin/js/hoocon-admin-lead-mail-reply.js"


def test_mailto_compose_url_prefills_recipient_subject_body() -> None:
    """mailto: carries to/subject/body for Yandex Mail and other MUAs."""
    url = build_mailto_compose_url(
        to="client@example.com",
        subject="КП #7 — ООО Ромашка",
        body="Комментарий клиента",
    )
    assert url.startswith("mailto:client@example.com?")
    assert "subject=" in url
    assert "body=" in url
    assert "yandexmail://" not in url


def test_yandex_web_compose_url_uses_full_mailto_payload() -> None:
    """Web compose embeds full mailto:… link in mailto= per Yandex handler."""
    url = build_yandex_compose_web_url(
        to="client@example.com",
        subject="КП #7 — ООО Ромашка",
        body="Комментарий клиента",
        from_email="mgr@yandex.ru",
    )
    assert url.startswith("https://mail.yandex.ru/compose?")
    assert "mailto=mailto%3Aclient%40example.com" in url
    assert "subject=" in url
    assert "body=" in url
    assert "from=mgr%40yandex.ru" in url
    decoded = unquote(url)
    assert "mailto:client@example.com" in decoded
    assert "Комментарий клиента" in decoded


def test_yandex_web_compose_com_host_for_yandex_com_mailbox() -> None:
    """@yandex.com mailboxes use mail.yandex.com compose."""
    url = build_yandex_compose_web_url(
        to="client@example.com",
        subject="Hi",
        from_email="mgr@yandex.com",
    )
    assert url.startswith("https://mail.yandex.com/compose?")


def test_android_intent_targets_yandex_mail_package() -> None:
    """Android intent opens ru.yandex.mail with SENDTO mailto payload."""
    mailto = build_mailto_compose_url(
        to="buyer@corp.ru",
        subject="КП",
        body="Нужны приводы",
    )
    intent = build_yandex_mail_android_intent_url(mailto)
    assert intent.startswith("intent:mailto:")
    assert "action=android.intent.action.SENDTO" in intent
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
    """Lead reply helper returns mailto + web + android intent."""
    urls = build_lead_reply_email_urls(
        lead_email="buyer@corp.ru",
        subject="КП #3 — Corp",
        manager_email="sales@hoocon.ru",
        body="Комментарий\n\nПозиции по заявке:\n- DA-01 × 2",
    )
    assert urls.web.startswith("https://mail.yandex.ru/compose")
    assert "mailto=mailto%3A" in urls.web
    assert urls.mailto.startswith("mailto:buyer@corp.ru")
    assert "subject=" in urls.mailto
    assert "body=" in urls.mailto
    assert "ru.yandex.mail" in urls.yandex_android


def test_lead_mail_reply_js_uses_mailto_not_yandexmail_scheme() -> None:
    """Loaded JS opens mailto for the native app; web is the fallback."""
    js = _MAIL_REPLY_JS.read_text(encoding="utf-8")
    assert "openMailto" in js
    assert "mailtoUrl" in js
    assert "dataset.mailtoUrl" in js
    assert "tryNativeThenWeb" in js


def test_format_lead_reply_subject_includes_pk_and_company() -> None:
    """Default KP subject uses lead id and company name."""
    from crm.mail_links import format_lead_reply_subject

    lead = Lead(
        pk=42,
        name="Клиент",
        email="client@example.com",
        company="ООО Ромашка",
    )
    assert format_lead_reply_subject(lead) == "КП #42 — ООО Ромашка"
