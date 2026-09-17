"""Triage guardrails: scope, URL whitelist, uncertain → manager."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from supportchat.gigachat.reply import generate_ai_reply
from supportchat.gigachat.triage_guard import (
    is_greeting_intent,
    response_has_disallowed_site_paths,
    response_misroutes_docs_to_catalog,
    triage_output_blocked,
    uncertain_branch_reply,
)
from supportchat.gigachat.triage_scope import triage_out_of_scope_reply
from supportchat.models import Channel, Conversation, Message, MessageDirection


def test_greeting_intent_matches_short_hello() -> None:
    assert is_greeting_intent("Добрый день")
    assert is_greeting_intent("Привет")
    assert is_greeting_intent("Чем можете помочь?")
    assert not is_greeting_intent("Нужен привод на заслонку 5 Нм")


def test_greeting_reply_static() -> None:
    from supportchat.gigachat.triage_guard import triage_greeting_reply

    reply = triage_greeting_reply("Привет")
    assert reply is not None
    assert "документац" in reply.lower()


def test_out_of_scope_gates_without_escalation() -> None:
    reply = triage_out_of_scope_reply("Нужен привод на гаражные ворота")
    assert reply is not None
    assert "ворот" in reply.lower() or "овк" in reply.lower()


def test_disallowed_site_path_detected() -> None:
    assert response_has_disallowed_site_paths("Смотрите /admin/secret") is True
    assert response_has_disallowed_site_paths("Каталог: /catalog") is False


def test_docs_misroute_to_catalog_blocked() -> None:
    bad = "Паспорт доступен в разделе каталога на сайте."
    assert response_misroutes_docs_to_catalog(bad, user_query="нужен паспорт на SA10FU24") is True
    assert triage_output_blocked(bad, user_query="нужен паспорт на SA10FU24") is True


def test_uncertain_model_phrase_blocked() -> None:
    assert triage_output_blocked("К сожалению, не знаю точный ответ.") is True


@pytest.mark.django_db
def test_unclear_question_offers_manager_branch_without_api(settings) -> None:
    """Вне сценариев → кнопки ветвления, без автоэскалации."""
    settings.GIGACHAT_MODE = "triage"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="guard-1")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Расскажите анекдот про вентиляцию",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert reply.text == uncertain_branch_reply()
    assert not reply.payload_extra.get("chat_actions")


@pytest.mark.django_db
def test_out_of_scope_before_product_clarify(settings) -> None:
    """Ворота → отказ, не уточнение по приводу."""
    settings.GIGACHAT_MODE = "triage"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="guard-gate")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен привод на гаражные ворота",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert "овк" in reply.text.lower()
