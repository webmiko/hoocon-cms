"""Bot tells visitors that shipping is only within Russia."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from supportchat.gigachat.reply import generate_ai_reply
from supportchat.gigachat.triage_delivery import triage_delivery_reply
from supportchat.models import Channel, Conversation, Message, MessageDirection


def test_delivery_reply_is_russia_only() -> None:
    """Вопрос о доставке → только Россия, без отказа в грубой форме."""
    reply = triage_delivery_reply("Доставляете ли в Казахстан?")
    assert reply is not None
    assert "только по России" in reply
    assert "пожалуйста" in reply
    assert "Беларус" not in reply


def test_manual_request_is_not_delivery() -> None:
    """Паспорт на модель не считается вопросом о доставке."""
    assert triage_delivery_reply("Пришлите паспорт на DA2MU24") is None


@pytest.mark.django_db
def test_delivery_reply_without_api(settings) -> None:
    """Вопрос о доставке закрывается без GigaChat и без эскалации."""
    settings.GIGACHAT_MODE = "full"
    settings.GIGACHAT_CREDENTIALS = "test-key"
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="delivery-1")
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Как организована доставка?",
    )

    with patch("supportchat.gigachat.reply.chat_completion") as api:
        reply = generate_ai_reply(conv)
        api.assert_not_called()

    assert reply.escalate is False
    assert "только по России" in reply.text
    assert "за её пределы" in reply.text
