"""GigaChat triage (cold chat) mode."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sitesettings.models import SiteSettings
from supportchat.gigachat.policy import ai_max_turns
from supportchat.gigachat.prompts import build_system_prompt
from supportchat.gigachat.reply import generate_ai_reply
from supportchat.gigachat.triage import (
    is_product_intent,
    is_triage_mode,
    parse_triage_escalation_note,
)
from supportchat.gigachat.triage_docs import build_docs_hub_path, triage_docs_reply
from supportchat.models import Channel, Conversation, Message, MessageDirection
from supportchat.services import add_inbound_message
from supportchat.tasks import gigachat_reply


@pytest.fixture
def gigachat_on(settings) -> SiteSettings:
    settings.GIGACHAT_CREDENTIALS = "test-key"
    settings.GIGACHAT_MODE = "triage"
    site = SiteSettings.load()
    site.gigachat_enabled = True
    site.ai_max_turns = 5
    site.save(update_fields=["gigachat_enabled", "ai_max_turns"])
    return site


def test_triage_mode_default(settings) -> None:
    """По умолчанию включён режим холодного чата."""
    settings.GIGACHAT_MODE = "triage"
    assert is_triage_mode() is True


def test_product_intent_detects_sku_and_keywords() -> None:
    """Детектор продуктовой темы для промпта и тестов."""
    assert is_product_intent("Какой момент у DA2MU?")
    assert is_product_intent("Нужен привод на заслонку")
    assert not is_product_intent("Здравствуйте")
    assert not is_product_intent("Где скачать документацию?")


def test_triage_docs_without_sku() -> None:
    """Общий вопрос про документы → /dokumentaciya без эскалации."""
    reply = triage_docs_reply("Где инструкции и паспорта?")
    assert reply is not None
    assert "/dokumentaciya" in reply


def test_triage_docs_with_sku_links_model_page() -> None:
    """Паспорт/инструкция на модель → /dokumentaciya?q=…&kind=…"""
    path = build_docs_hub_path("Нужен паспорт на DA2MU24")
    assert path == "/dokumentaciya?q=DA2MU24&kind=passport"
    reply = triage_docs_reply("Инструкция DA2MU24-D")
    assert reply is not None
    assert "/dokumentaciya?q=" in reply
    assert "DA2MU24" in reply


@pytest.mark.django_db
def test_triage_prompt_has_no_kb(settings) -> None:
    """В triage промпт не подмешивает gigachat_kb.txt."""
    settings.GIGACHAT_MODE = "triage"
    prompt = build_system_prompt(user_query="Привет")
    assert "холодный чат" in prompt.lower()
    assert "gigachat_kb" not in prompt.lower()
    assert "для менеджера" in prompt.lower()


def test_parse_triage_escalation_note_extracts_summary() -> None:
    """Сводка для менеджера парсится из ответа бота."""
    text = "Для менеджера: заслонка, 5 Н·м, 24 В, 3 шт.\nПодключаю менеджера, он подберёт решение."
    assert parse_triage_escalation_note(text) == "заслонка, 5 Н·м, 24 В, 3 шт."


@pytest.mark.django_db
def test_triage_product_question_asks_without_api(gigachat_on) -> None:
    """Вопрос о продукции → статическое уточнение без GigaChat API."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="triage-1")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен привод на заслонку 5 Нм",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert reply.product_clarify is True
    assert "напряжение" in reply.text.lower()


@pytest.mark.django_db
def test_triage_explicit_manager_escalates_without_api(gigachat_on) -> None:
    """Просьба менеджера → сразу handoff без GigaChat API."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="triage-mgr")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Позовите менеджера",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is True
    assert "менеджер" in reply.text.lower()


@pytest.mark.django_db
def test_triage_docs_nav_without_api(gigachat_on) -> None:
    """Вопрос про документацию → ссылка на раздел без GigaChat API."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="triage-nav")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Где скачать инструкции?",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert "/dokumentaciya" in reply.text


@pytest.mark.django_db
def test_triage_greeting_static_without_api(gigachat_on) -> None:
    """Приветствие — статический ответ без GigaChat API."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="triage-2")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Привет",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert "помочь" in reply.text.lower()


@pytest.mark.django_db
def test_triage_privet_task_delivers_reply(gigachat_on) -> None:
    """Celery: «Привет» → ответ бота в диалоге."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="triage-privet")
    inbound, _ = add_inbound_message(conv, "Привет")

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        result = gigachat_reply(conv.pk, inbound.pk)
        api.assert_not_called()

    assert result == "ok"
    ai_msgs = Message.objects.filter(
        conversation=conv,
        direction=MessageDirection.SYSTEM,
        raw_payload__ai=True,
    )
    assert ai_msgs.count() == 1
    assert "помочь" in ai_msgs.first().body.lower()


@pytest.mark.django_db
def test_triage_privet_after_outside_hours_auto_reply(gigachat_on) -> None:
    """Вне часов: автоответ не ломает ответ бота на «Привет»."""
    from supportchat.schedule import ensure_default_schedule

    schedule = ensure_default_schedule()
    schedule.auto_reply_outside_hours = "Сейчас нерабочее время, ответим позже."
    schedule.save(update_fields=["auto_reply_outside_hours"])

    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="triage-oos")
    with patch("supportchat.services.is_open_now", return_value=False):
        inbound, auto = add_inbound_message(conv, "Привет")

    assert auto is not None
    with patch("supportchat.gigachat.reply.chat_completion") as api:
        result = gigachat_reply(conv.pk, inbound.pk)
        api.assert_not_called()

    assert result == "ok"
    ai_msg = Message.objects.filter(
        conversation=conv,
        direction=MessageDirection.SYSTEM,
        raw_payload__ai=True,
    ).first()
    assert ai_msg is not None
    assert "помочь" in ai_msg.body.lower()


@pytest.mark.django_db
def test_triage_task_continues_after_clarification_without_escalation(gigachat_on) -> None:
    """Celery: после уточнения бот отвечает текстом, без автоэскалации и без кнопок."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="triage-3")
    first, _ = add_inbound_message(conv, "Подберите привод на заслонку 1 кв.м")
    assert gigachat_reply(conv.pk, first.pk) == "ok"

    second, _ = add_inbound_message(conv, "24 В, перепад 100 Па")
    with patch("supportchat.gigachat.reply.chat_completion") as api:
        result = gigachat_reply(conv.pk, second.pk)
        api.assert_not_called()

    assert result == "ok"
    conv.refresh_from_db()
    assert conv.ai_escalated_at is None
    followup = (
        Message.objects.filter(
            conversation=conv,
            direction=MessageDirection.SYSTEM,
            raw_payload__ai=True,
        )
        .order_by("-id")
        .first()
    )
    assert followup is not None
    assert "позовите менеджера" in followup.body.lower()
    payload = followup.raw_payload if isinstance(followup.raw_payload, dict) else {}
    assert not payload.get("chat_actions")


@pytest.mark.django_db
def test_triage_limits_turns(gigachat_on) -> None:
    """В triage до 4 ответов бота (приветствие + уточнения)."""
    assert ai_max_turns() == 4
