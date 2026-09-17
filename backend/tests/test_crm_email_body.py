"""CRM email body helpers: HTML detection and multipart plain fallback."""

from __future__ import annotations

from crm.email_body import html_email_to_plain, is_html_email_body
from crm.manager_signatures import (
    assemble_lead_reply_body,
    manager_reply_signature,
    manager_reply_signature_html,
)


def test_is_html_email_body_detects_rich_text() -> None:
    """HTML compose stores tags that should trigger multipart send."""
    assert is_html_email_body("<p>Hello</p>")
    assert not is_html_email_body("Hello\n\nWorld")


def test_html_email_to_plain_strips_markup() -> None:
    """Multipart alternative includes a readable plain body."""
    plain = html_email_to_plain("<p><strong>КП</strong><br>готово</p>")
    assert "КП" in plain
    assert "готово" in plain
    assert "<" not in plain


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


def test_manager_reply_signature_html_supports_legacy_mailto_and_tel_lines() -> None:
    """Legacy signature lines with mailto:/tel: suffixes still linkify in HTML."""
    from crm.manager_signatures import _MANAGER_SIGNATURES

    _MANAGER_SIGNATURES["legacy@hoocon.ru"] = (
        "Legacy\n+7(900)000-00-00 (tel:+79000000000)\nmailto:legacy@hoocon.ru"
    )
    html = manager_reply_signature_html("legacy@hoocon.ru")
    assert 'href="tel:+79000000000"' in html
    assert 'href="mailto:legacy@hoocon.ru"' in html
    del _MANAGER_SIGNATURES["legacy@hoocon.ru"]


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
