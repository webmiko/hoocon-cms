"""Chat: tabs over the inbox and the «what to do now» strip over the thread."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.chat_card import build_chat_card
from crm.models import Client
from supportchat.models import Conversation, ConversationStatus, Message, MessageDirection

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


_COUNTER = 0


def _chat(**extra: Any) -> Conversation:
    global _COUNTER
    _COUNTER += 1
    fields: dict[str, Any] = {
        "channel": "web",
        "external_user_id": f"visitor-{_COUNTER}",
        "display_name": f"Посетитель {_COUNTER}",
        "last_message_at": timezone.now(),
        **extra,
    }
    chat = Conversation.objects.create(**fields)
    Message.objects.create(conversation=chat, direction=MessageDirection.INBOUND, body="Здравствуйте, нужна цена")
    return chat


def _labels(card: Any) -> list[str]:
    return [button.label for button in card.buttons]


@pytest.mark.django_db
def test_free_dialog_asks_to_be_taken() -> None:
    card = build_chat_card(_chat(), _manager("cc-free"))

    assert card.state == "free"
    assert card.buttons[0].label == "Взять диалог"
    assert card.buttons[0].post is True


@pytest.mark.django_db
def test_my_dialog_with_a_client_offers_quote_and_close() -> None:
    manager = _manager("cc-mine")
    person = Client.objects.create(name="Иван", email="cc-mine@klimat.ru")
    card = build_chat_card(_chat(assignee=manager, client=person), manager)

    assert card.state == "mine"
    assert _labels(card) == ["Создать КП", "Карточка клиента", "Закрыть диалог"]


@pytest.mark.django_db
def test_my_dialog_without_a_client_asks_for_contacts() -> None:
    manager = _manager("cc-anon")
    card = build_chat_card(_chat(assignee=manager), manager)

    assert "Создать КП" not in _labels(card)
    assert "почту или телефон" in card.hint


@pytest.mark.django_db
def test_colleagues_dialog_has_no_actions_and_closed_dialog_says_so() -> None:
    manager = _manager("cc-me")
    other = _manager("cc-other")

    assert build_chat_card(_chat(assignee=other), manager).state == "other"
    assert build_chat_card(_chat(status=ConversationStatus.CLOSED), manager).state == "closed"


@pytest.mark.django_db
def test_thread_page_shows_the_strip_outside_the_form() -> None:
    manager = _manager("cc-page")
    chat = _chat()
    http = HttpClient()
    http.force_login(manager)

    html = http.get(reverse("admin:supportchat_conversation_change", args=[chat.pk])).content.decode()

    assert "Что делать сейчас" in html
    assert "Взять диалог" in html
    assert html.index("Что делать сейчас") < html.index('id="conversation_form"')


@pytest.mark.django_db
def test_take_chat_assigns_once_and_does_not_steal() -> None:
    manager = _manager("cc-take")
    other = _manager("cc-owner")
    free = _chat()
    busy = _chat(assignee=other)
    http = HttpClient()
    http.force_login(manager)

    http.post(reverse("crm-workspace-take-chat", args=[free.pk]))
    http.post(reverse("crm-workspace-take-chat", args=[busy.pk]))

    free.refresh_from_db()
    busy.refresh_from_db()
    assert free.assignee_id == manager.pk
    assert busy.assignee_id == other.pk


@pytest.mark.django_db
def test_close_chat_closes_mine_and_refuses_a_colleagues() -> None:
    manager = _manager("cc-close")
    other = _manager("cc-keeper")
    mine = _chat(assignee=manager)
    theirs = _chat(assignee=other)
    http = HttpClient()
    http.force_login(manager)

    http.post(reverse("crm-workspace-close-chat", args=[mine.pk]))
    http.post(reverse("crm-workspace-close-chat", args=[theirs.pk]))

    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.status == ConversationStatus.CLOSED
    assert theirs.status == ConversationStatus.OPEN
    assert http.get(reverse("crm-workspace-close-chat", args=[mine.pk])).status_code == 405


@pytest.mark.django_db
def test_inbox_tabs_count_and_open() -> None:
    manager = _manager("cc-tabs")
    _chat(staff_unread_count=2)
    _chat(assignee=manager)
    _chat(status=ConversationStatus.CLOSED)
    http = HttpClient()
    http.force_login(manager)

    response = http.get(reverse("admin:supportchat_conversation_changelist"))
    tabs = {tab.label: tab for tab in response.context_data["hoocon_tabs"]}

    assert "hoocon-tabs" in response.content.decode()
    assert tabs["Непрочитанные"].count == 1
    assert tabs["Мои"].count == 1
    assert tabs["Закрытые"].count == 1
    for tab in tabs.values():
        assert http.get(reverse("admin:supportchat_conversation_changelist") + tab.url).status_code == 200, tab.label
