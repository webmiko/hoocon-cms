"""CRM email body helpers: HTML detection and multipart plain fallback."""

from __future__ import annotations

import re

import pytest
from django.urls import reverse

from crm.email_body import email_body_for_reading, html_email_to_plain, is_html_email_body
from crm.manager_signatures import (
    assemble_lead_reply_body,
    manager_reply_signature,
    manager_reply_signature_html,
)
from crm.models import Client, EmailMessage, EmailStatus


def test_is_html_email_body_detects_rich_text() -> None:
    """HTML compose stores tags that should trigger multipart send."""
    assert is_html_email_body("<p>Hello</p>")
    assert not is_html_email_body("Hello\n\nWorld")


def test_html_email_to_plain_strips_markup() -> None:
    """Multipart alternative includes a readable plain body."""
    plain = html_email_to_plain("<p><strong>КП</strong><br>готово</p>")
    assert plain == "КП\nготово"
    assert "<" not in plain


def test_html_email_to_plain_keeps_paragraphs_and_decodes_entities() -> None:
    """Letter-card text is paragraphs, not tags or &nbsp;."""
    plain = html_email_to_plain("<p><p>Здравствуйте, Владимир!</p><p>Каталог:&nbsp;https://hoocon.ru/catalog</p>")
    assert plain == "Здравствуйте, Владимир!\n\nКаталог: https://hoocon.ru/catalog"


def test_html_email_to_plain_keeps_link_address() -> None:
    """A link stays readable when the tags are removed."""
    plain = html_email_to_plain('<p>Можно <a href="https://hoocon.ru/catalog">открыть каталог</a>.</p>')
    assert plain == "Можно открыть каталог (https://hoocon.ru/catalog)."


def test_email_body_for_reading_leaves_plain_text() -> None:
    """Ordinary letters are not rewritten."""
    text = "Добрый день!\n\nСчёт во вложении."
    assert email_body_for_reading(text) == text


def test_email_body_for_reading_strips_img_and_iframe() -> None:
    """Inbound plain that is not a <p> still must not keep active tags."""
    text = email_body_for_reading(
        'Смотрите <img src="x" onerror="alert(1)"> и <iframe src="https://evil.test"></iframe> конец'
    )
    assert text == "Смотрите  и  конец"
    assert "<" not in text
    assert "onerror" not in text


def test_html_email_to_plain_strips_tags_restored_by_unescape() -> None:
    """&lt;script&gt; must not become a live tag after entity decoding."""
    plain = html_email_to_plain("<p>Текст &lt;script&gt;alert(1)&lt;/script&gt;</p>")
    assert plain == "Текст alert(1)"
    assert "<" not in plain


_CARD_HTML = "<p><p>Здравствуйте, Владимир!</p><p>Каталог:&nbsp;https://hoocon.ru/catalog</p>"
_CARD_PLAIN = "Здравствуйте, Владимир!\n\nКаталог: https://hoocon.ru/catalog"


@pytest.mark.django_db
def test_email_change_form_shows_body_without_tags(client, django_user_model) -> None:
    """Карточка письма показывает текст, а не HTML-теги в textarea."""
    user = django_user_model.objects.create_user(
        username="crm-body-plain",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Владимир", email="buyer@example.com")
    msg = EmailMessage.objects.create(
        client=crm_client,
        to_email="buyer@example.com",
        from_email="assistant@hoocon.ru",
        subject="После выставки",
        body=_CARD_HTML,
        status=EmailStatus.SENT,
    )
    client.force_login(user)
    html = client.get(reverse("admin:crm_emailmessage_change", args=[msg.pk])).content.decode()
    match = re.search(r'<textarea[^>]*\bname="body"[^>]*>(.*?)</textarea>', html, re.DOTALL)
    assert match is not None
    shown = match.group(1)
    assert shown == _CARD_PLAIN
    assert "<p>" not in shown
    assert "&lt;p&gt;" not in shown
    assert "&nbsp;" not in shown


@pytest.mark.django_db
def test_email_change_form_saves_body_without_tags(client, django_user_model) -> None:
    """Сохранение карточки не оставляет в теле вставленный HTML."""
    user = django_user_model.objects.create_user(
        username="crm-body-save",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    crm_client = Client.objects.create(name="Владимир", email="buyer-save@example.com")
    msg = EmailMessage.objects.create(
        client=crm_client,
        to_email="buyer-save@example.com",
        from_email="assistant@hoocon.ru",
        subject="После выставки",
        body="Черновик",
        status=EmailStatus.DRAFT,
    )
    client.force_login(user)
    url = reverse("admin:crm_emailmessage_change", args=[msg.pk])
    page = client.get(url).content.decode()
    management = {
        name: value
        for name, value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', page)
        if "-TOTAL_FORMS" in name or "-INITIAL_FORMS" in name or "-MIN_NUM_FORMS" in name or "-MAX_NUM_FORMS" in name
    }
    response = client.post(
        url,
        {
            "client": crm_client.pk,
            "status": EmailStatus.DRAFT,
            "to_email": "buyer-save@example.com",
            "reply_to_email": "",
            "lead": "",
            "subject": "После выставки",
            "body": _CARD_HTML,
            **management,
        },
    )
    assert response.status_code == 302, response.content.decode()[:1500]
    msg.refresh_from_db()
    assert msg.body == _CARD_PLAIN
    assert "<" not in msg.body


def test_manager_reply_signature_html_linkifies_phone_and_email() -> None:
    """Clean signature lines become clickable tel/mailto links in HTML."""
    html = manager_reply_signature_html("assistant@hoocon.ru")
    assert 'href="tel:+79957807018"' in html
    assert "+7(995)780-70-18" in html
    assert 'href="mailto:assistant@hoocon.ru"' in html
    assert "С уважением, Людмила" in html


def test_manager_reply_signature_plain_text_for_ludmila() -> None:
    """Plain signature has no mailto:/tel: prefixes for managers."""
    plain = manager_reply_signature("assistant@hoocon.ru")
    assert plain.startswith("С уважением, Людмила")
    assert "assistant@hoocon.ru" in plain
    assert "mailto:" not in plain


def test_manager_reply_signature_unknown_email_returns_empty() -> None:
    """Unconfigured manager mailboxes do not get a signature block."""
    assert manager_reply_signature("") == ""
    assert manager_reply_signature("other@hoocon.ru") == ""


def test_signature_contacts_come_from_settings(settings) -> None:
    """Контакты подписи были зашиты в модуль; мёртвые ветки mailto:/tel: разбирали несуществующий формат."""
    settings.MANAGER_SIGNATURE_CONTACTS = {
        "Sales@Hoocon.ru": {"name": "Ирина", "company": "ООО <Хогон>", "phone": "+7 900 000-00-00"},
    }
    html = manager_reply_signature_html("sales@hoocon.ru")
    assert 'href="tel:+79000000000"' in html
    assert 'href="mailto:sales@hoocon.ru"' in html
    assert "ООО &lt;Хогон&gt;" in html
    assert manager_reply_signature("sales@hoocon.ru").splitlines() == [
        "С уважением, Ирина",
        "ООО <Хогон>",
        "+7 900 000-00-00",
        "sales@hoocon.ru",
    ]
    assert manager_reply_signature("assistant@hoocon.ru") == ""


def test_assemble_lead_reply_body_appends_plain_signature() -> None:
    """Plain-text replies append Ludmila signature and footer."""
    body = assemble_lead_reply_body("Добрый день!", "assistant@hoocon.ru")
    assert body.startswith("Добрый день!")
    assert "С уважением, Людмила" in body
    assert "Ответьте на это письмо" in body


def test_assemble_lead_reply_body_appends_html_signature() -> None:
    """HTML replies keep Ludmila signature and footer as HTML fragments."""
    body = assemble_lead_reply_body(
        "<p>Добрый день!</p>",
        "assistant@hoocon.ru",
    )
    assert body.startswith("<p>Добрый день!</p>")
    assert 'href="mailto:assistant@hoocon.ru"' in body
    assert "С уважением, Людмила" in body
    assert "Ответьте на это письмо" in body
