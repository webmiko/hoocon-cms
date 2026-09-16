"""Triage documentation links to /dokumentaciya for specific models."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from supportchat.gigachat.reply import generate_ai_reply
from supportchat.gigachat.triage_docs import build_docs_hub_path, triage_docs_reply
from supportchat.models import Channel, Conversation, Message, MessageDirection


@pytest.mark.django_db
def test_docs_with_sku_uses_hub_without_api(settings) -> None:
    """Паспорт на артикул → ссылка на /dokumentaciya?q=… без GigaChat."""
    settings.GIGACHAT_MODE = "triage"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="docs-sku")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Пришлите паспорт на DA2MU24",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert "kind=passport" in reply.text
    assert "DA2MU24" in reply.text


def test_manual_kind_in_path() -> None:
    """Запрос инструкции → kind=manual в ссылке."""
    reply = triage_docs_reply("Где инструкция DA2MU24?")
    assert reply is not None
    assert "kind=manual" in reply


def test_safu_passport_path_preserves_ds_suffix() -> None:
    """Паспорт на SA10FU24-DS → полный артикул в ссылке."""
    path = build_docs_hub_path("нужен паспорт на sa10fu24-ds")
    assert path == "/dokumentaciya?q=SA10FU24-DS&kind=passport"
    reply = triage_docs_reply("нужен паспорт на sa10fu24-ds")
    assert reply is not None
    assert "каталог" not in reply.lower()


def test_dafu_passport_path_preserves_suffix() -> None:
    """Паспорт на DA5FU230-D → полный артикул в ссылке."""
    path = build_docs_hub_path("нужен паспорт на da5fu230-d")
    assert path == "/dokumentaciya?q=DA5FU230-D&kind=passport"
    reply = triage_docs_reply("нужен паспорт на da5fu230-d")
    assert reply is not None
    assert "DA5FU230-D" in reply
    assert "недоступ" not in reply.lower()


@pytest.mark.django_db
def test_docs_with_sku_works_in_full_mode_without_api(settings) -> None:
    """Паспорт/инструкция обрабатываются статически и в full mode."""
    settings.GIGACHAT_MODE = "full"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="docs-full")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="нужен паспорт на da5fu230-d",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert "/dokumentaciya?q=DA5FU230-D" in reply.text
