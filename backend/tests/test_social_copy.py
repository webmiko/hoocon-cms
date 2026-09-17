"""Messenger bots share contact copy via social.copy."""

from __future__ import annotations

from social.copy import INN, PHONE, compose_contacts_html, compose_contacts_plain
from social.max_bot import compose_contacts_text
from social.telegram_bot import compose_contacts_caption


def test_contacts_plain_and_html_include_phone_and_inn() -> None:
    """MAX plain and Telegram HTML contacts cite the same canonical phone/INN."""
    plain = compose_contacts_plain()
    html = compose_contacts_html()
    assert PHONE in plain
    assert INN in plain
    assert PHONE in html
    assert INN in html


def test_bot_wrappers_use_shared_copy() -> None:
    """Bot compose helpers delegate to social.copy without drift."""
    assert compose_contacts_text() == compose_contacts_plain(limit=4000)
    assert compose_contacts_caption() == compose_contacts_html(limit=1024)
