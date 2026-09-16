"""Triage product selection: clarify, no model picks."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from supportchat.gigachat.reply import generate_ai_reply
from supportchat.gigachat.triage_product import (
    triage_product_clarification_reply,
    triage_response_violates_policy,
)
from supportchat.models import Channel, Conversation, Message, MessageDirection


def test_violates_policy_catches_kb_style_answer() -> None:
    """Ответ с веткой manual.* и DA2MU — запрещён в triage."""
    text = "## [manual.DA2MU] Руководство\nрекомендуем привод DA2MU 2 Н·м для заслонки 1 кв.м"
    assert triage_response_violates_policy(text) is True


def test_clarification_for_damper_area_mentions_quiz() -> None:
    """Первый ответ про заслонку — вопросы, каталог и квиз, без модели."""
    reply = triage_product_clarification_reply("нужен привод для заслонки 1 кв.м")
    lowered = reply.lower()
    assert "da2mu" not in lowered
    assert "рекомендуем" not in lowered
    assert "/#podbor" in reply
    assert "напряжение" in lowered


@pytest.mark.django_db
def test_product_question_uses_static_clarification_without_api(settings) -> None:
    """Подбор по площади → статическое уточнение без GigaChat API."""
    settings.GIGACHAT_MODE = "triage"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="prod-clarify")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="нужен привод для заслонки 1 кв.м",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert reply.product_clarify is True
    assert "/#podbor" in reply.text


@pytest.mark.django_db
def test_product_followup_escalates_to_manager(settings) -> None:
    """После уточнения клиент отвечает → передача менеджеру."""
    settings.GIGACHAT_MODE = "triage"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="prod-follow")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="нужен привод для заслонки 1 кв.м",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.SYSTEM,
        body="Уточните напряжение",
        raw_payload={"ai": True, "ai_product_clarify": True},
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="24 В, перепад 100 Па",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is True
    assert "менеджер" in reply.text.lower()
    assert "24 В" in reply.escalation_note
