"""GigaChat assistant in support chat."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sitesettings.models import SiteSettings
from supportchat.gigachat.reply import AiReply
from supportchat.models import Channel, Conversation, Message, MessageDirection
from supportchat.services import add_inbound_message, add_staff_reply, message_sender_name
from supportchat.tasks import gigachat_reply


@pytest.fixture
def gigachat_on(settings) -> SiteSettings:
    settings.GIGACHAT_CREDENTIALS = "test-key"
    site = SiteSettings.load()
    site.gigachat_enabled = True
    site.gigachat_model = "GigaChat-2"
    site.ai_max_turns = 5
    site.save(update_fields=["gigachat_enabled", "gigachat_model", "ai_max_turns"])
    return site


@pytest.mark.django_db
def test_ai_reply_creates_system_message(gigachat_on) -> None:
    """Inbound + Celery task → SYSTEM reply from GigaChat."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="sess-1")
    inbound, _auto = add_inbound_message(conv, "Какой привод для откатных ворот?")

    with patch("supportchat.gigachat.reply.generate_ai_reply") as gen:
        gen.return_value = AiReply(
            text="Для откатных ворот подойдёт серия DA…",
            escalate=False,
            escalation_note="",
        )
        result = gigachat_reply(conv.pk, inbound.pk)

    assert result == "ok"
    system = Message.objects.filter(conversation=conv, direction=MessageDirection.SYSTEM).first()
    assert system is not None
    assert "DA" in system.body
    assert system.raw_payload == {"ai": True}
    conv.refresh_from_db()
    assert conv.ai_turn_count == 1


@pytest.mark.django_db
def test_ai_skipped_when_disabled(settings) -> None:
    """Без gigachat_enabled задача не ставится из add_inbound_message."""
    settings.GIGACHAT_CREDENTIALS = "test-key"
    site = SiteSettings.load()
    site.gigachat_enabled = False
    site.save(update_fields=["gigachat_enabled"])
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="sess-2")

    with patch("supportchat.tasks.gigachat_reply.delay") as delay:
        add_inbound_message(conv, "Привет")
        delay.assert_not_called()


@pytest.mark.django_db
def test_ai_escalation_after_max_turns(gigachat_on) -> None:
    """Лимит ходов ассистента → эскалация менеджеру."""
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-3",
        ai_turn_count=5,
    )
    inbound, _ = add_inbound_message(conv, "Ещё вопрос")

    result = gigachat_reply(conv.pk, inbound.pk)
    assert result.startswith("escalated:turn_limit")
    conv.refresh_from_db()
    assert conv.ai_escalated_at is not None
    assert conv.ai_active is False
    handoff = Message.objects.filter(
        conversation=conv,
        direction=MessageDirection.SYSTEM,
        raw_payload__ai_handoff=True,
    ).first()
    assert handoff is not None


@pytest.mark.django_db
def test_staff_reply_disables_ai(gigachat_on, django_user_model) -> None:
    """Ответ менеджера отключает ассистента в диалоге."""
    user = django_user_model.objects.create_user(
        username="mgr",
        email="mgr@example.com",
        password="x",
        is_staff=True,
    )
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="sess-4", ai_active=True)
    add_staff_reply(conv, "Здравствуйте, чем помочь?", author=user)
    conv.refresh_from_db()
    assert conv.ai_active is False


@pytest.mark.django_db
def test_ai_first_reply_discloses_bot(gigachat_on) -> None:
    """Первый ответ бота явно говорит, что это не менеджер."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="sess-bot")
    inbound, _ = add_inbound_message(conv, "Добрый день")

    with patch("supportchat.gigachat.reply.generate_ai_reply") as gen:
        gen.return_value = AiReply(
            text="Чем могу помочь?",
            escalate=False,
            escalation_note="",
        )
        gigachat_reply(conv.pk, inbound.pk)

    system = Message.objects.filter(conversation=conv, direction=MessageDirection.SYSTEM).first()
    assert system is not None
    assert "автоматический помощник" in system.body.lower()
    assert message_sender_name(system) == "Бот Hoocon"


@pytest.mark.django_db
def test_ai_escalation_skips_duplicate_handoff(gigachat_on) -> None:
    """При эскалации с текстом бота не дублируем системное handoff-сообщение."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="sess-handoff")
    inbound, _ = add_inbound_message(conv, "Подберите привод")

    with patch("supportchat.gigachat.reply.generate_ai_reply") as gen:
        gen.return_value = AiReply(
            text="Переключаю чат на менеджера.",
            escalate=True,
            escalation_note="продукт",
        )
        result = gigachat_reply(conv.pk, inbound.pk)

    assert result.startswith("escalated:")
    system_rows = Message.objects.filter(conversation=conv, direction=MessageDirection.SYSTEM)
    assert system_rows.count() == 1
    assert not system_rows.filter(raw_payload__ai_handoff=True).exists()


@pytest.mark.django_db
def test_ai_delivers_to_telegram(gigachat_on) -> None:
    """SYSTEM-ответ ассистента уходит в Telegram."""
    conv = Conversation.objects.create(channel=Channel.TELEGRAM, external_user_id="12345")
    inbound, _ = add_inbound_message(conv, "Где купить?")

    from social.publishers import PublishResult

    with (
        patch("supportchat.gigachat.reply.generate_ai_reply") as gen,
        patch("social.publishers.publish_telegram") as publish,
    ):
        gen.return_value = AiReply(text="Смотрите /gde-kupit", escalate=False, escalation_note="")
        publish.return_value = PublishResult(ok=True)
        gigachat_reply(conv.pk, inbound.pk)
        publish.assert_called_once()
