"""Absolute site links in messenger bot replies."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from supportchat.gigachat.delivery import deliver_ai_message
from supportchat.gigachat.site_links import expand_site_links_for_messenger
from supportchat.models import Channel, Conversation, Message, MessageDirection


def test_expand_docs_link_with_query() -> None:
    """Паспорт → полный URL с q и kind для Telegram/MAX."""
    text = "Паспорт по модели SA10FU24-DS — на странице документации: /dokumentaciya?q=SA10FU24-DS&kind=passport."
    expanded = expand_site_links_for_messenger(text, base_url="https://hoocon.ru")
    assert (
        expanded == "Паспорт по модели SA10FU24-DS — на странице документации: "
        "https://hoocon.ru/dokumentaciya?q=SA10FU24-DS&kind=passport."
    )


def test_expand_skips_already_absolute() -> None:
    """Не дублируем базу, если ссылка уже абсолютная."""
    url = "https://hoocon.ru/dokumentaciya?q=DA2MU24"
    assert expand_site_links_for_messenger(url, base_url="https://hoocon.ru") == url


def test_expand_home_anchor() -> None:
    """Подбор на главной → полный URL с якорем."""
    text = "Квиз подбора — /#podbor."
    assert expand_site_links_for_messenger(text, base_url="https://hoocon.ru") == (
        "Квиз подбора — https://hoocon.ru/#podbor."
    )


@pytest.mark.django_db
def test_deliver_ai_message_expands_links_for_telegram() -> None:
    """В Telegram уходит текст с https://, в БД остаётся относительный путь."""
    conv = Conversation.objects.create(
        channel=Channel.TELEGRAM,
        external_user_id="12345",
    )
    msg = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.SYSTEM,
        body="Документация: /dokumentaciya?q=SA10FU24-DS&kind=passport",
        raw_payload={"ai": True},
    )

    with patch("social.publishers.publish_telegram") as publish:
        publish.return_value = type("R", (), {"ok": True, "error": ""})()
        deliver_ai_message(conv, msg)

    publish.assert_called_once()
    sent = publish.call_args.kwargs["text"]
    assert "https://hoocon.ru/dokumentaciya?q=SA10FU24-DS&amp;kind=passport" in sent
    msg.refresh_from_db()
    assert "/dokumentaciya?q=SA10FU24-DS" in msg.body
    assert "https://hoocon.ru" not in msg.body
