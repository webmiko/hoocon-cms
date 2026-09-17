"""Triage product selection: clarify, no model picks."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from supportchat.gigachat.reply import generate_ai_reply
from supportchat.gigachat.triage import triage_site_nav_reply
from supportchat.gigachat.triage_product import (
    triage_product_clarification_reply,
    triage_response_violates_policy,
)
from supportchat.models import Channel, Conversation, Message, MessageDirection


def test_violates_policy_catches_kb_style_answer() -> None:
    """Ответ с веткой manual.* и DA2MU — запрещён в triage."""
    text = "## [manual.DA2MU] Руководство\nрекомендуем привод DA2MU 2 Н·м для заслонки 1 кв.м"
    assert triage_response_violates_policy(text) is True


def test_site_nav_skips_catalog_for_multi_series_product_request() -> None:
    """Серии DA/SA/HVA/HVD — не общий ответ /catalog, а product clarification."""
    text = "Нам нужны электропривода 24В, серии DA, SA, HVA, HVD торговая марка HOOCON."
    assert triage_site_nav_reply(text) is None


def test_multi_series_clarification_lists_catalog_categories() -> None:
    """B2B-запрос по четырём сериям — ссылки на категории и напряжение 24 В."""
    text = "Нам нужны электропривода 24В, серии DA, SA, HVA, HVD торговая марка HOOCON."
    reply = triage_product_clarification_reply(text)
    lowered = reply.lower()
    assert "фильтры по моменту" not in lowered
    assert "/catalog/elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata" in reply
    assert "/catalog/elektroprivody-protivopozharnye-i-dymovye" in reply
    assert "/catalog/elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata" in reply
    assert "24 в" in lowered
    assert "/rfq" in reply


def test_clarification_for_damper_area_mentions_quiz() -> None:
    """Первый ответ про заслонку — вопросы, каталог и квиз, без модели."""
    reply = triage_product_clarification_reply("нужен привод для заслонки 1 кв.м")
    lowered = reply.lower()
    assert "da2mu" not in lowered
    assert "рекомендуем" not in lowered
    assert "/#podbor" in reply
    assert "напряжение" in lowered


@pytest.mark.django_db
def test_multi_series_product_uses_static_clarification_without_api(settings) -> None:
    """Четыре серии + 24 В → категории каталога без GigaChat API."""
    settings.GIGACHAT_MODE = "triage"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="multi-series")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body=("Нам нужны электропривода 24В, серии DA, SA, HVA, HVD торговая марка HOOCON."),
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert reply.product_clarify is True
    assert "/catalog/elektroprivody-protivopozharnye-i-dymovye" in reply.text
    assert "фильтры по моменту" not in reply.text.lower()


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
def test_product_followup_keeps_bot_without_manager_button(settings) -> None:
    """После уточнения бот продолжает диалог; менеджер — только по явной просьбе."""
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

    assert reply.escalate is False
    assert "позовите менеджера" in reply.text.lower()
    assert not reply.payload_extra.get("chat_actions")


@pytest.mark.django_db
def test_call_manager_action_escalates_with_thread_summary(settings) -> None:
    """Кнопка «Позвать менеджера» → handoff со сводкой из переписки."""
    settings.GIGACHAT_MODE = "triage"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="prod-action")
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
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Позвать менеджера",
        raw_payload={"chat_action": "call_manager"},
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv, inbound_message=inbound)
        api.assert_not_called()

    assert reply.escalate is True
    assert "заслонк" in reply.escalation_note.lower()
