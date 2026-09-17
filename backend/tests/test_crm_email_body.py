"""CRM email body helpers: HTML detection and multipart plain fallback."""

from __future__ import annotations

from crm.email_body import html_email_to_plain, is_html_email_body
from crm.manager_signatures import assemble_lead_reply_body


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
