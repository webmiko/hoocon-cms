"""Support chat robustness: chitchat, branch actions, debounce, housekeeping."""

from __future__ import annotations

import html
from datetime import timedelta

import pytest
from django.utils import timezone

from sitesettings.models import SiteSettings
from supportchat.admin import AwaitingManagerFilter, ConversationAdmin, HasMessagesFilter
from supportchat.models import (
    Channel,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
)
from supportchat.services import add_inbound_message, add_staff_reply, inbound_superseded
from supportchat.tasks import gigachat_reply, supportchat_housekeeping


@pytest.fixture
def gigachat_on(settings, monkeypatch: pytest.MonkeyPatch) -> SiteSettings:
    """Assistant enabled in triage mode (no network calls in tests)."""
    settings.GIGACHAT_CREDENTIALS = "test-key"
    settings.GIGACHAT_MODE = "triage"
    site = SiteSettings.load()
    site.gigachat_enabled = True
    site.ai_max_turns = 5
    site.save(update_fields=["gigachat_enabled", "ai_max_turns"])
    monkeypatch.setattr("supportchat.services.is_open_now", lambda: True)
    return site


_session_seq = 0


def _conversation(**kwargs) -> Conversation:
    global _session_seq  # noqa: PLW0603 — уникальный id сессии на каждый диалог
    _session_seq += 1
    kwargs.setdefault("channel", Channel.WEB)
    kwargs.setdefault("external_user_id", f"sess-{_session_seq}")
    return Conversation.objects.create(**kwargs)


def _inbound(conv: Conversation, body: str, **kwargs) -> Message:
    return Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body=body,
        **kwargs,
    )


@pytest.mark.django_db
def test_chitchat_joke_gets_polite_refusal_no_escalation(gigachat_on) -> None:
    """«Расскажи анекдот» больше не убивает бота эскалацией менеджеру."""
    from supportchat.gigachat.reply import generate_ai_reply

    conv = _conversation()
    inbound = _inbound(conv, "анекдот расскажешь?")

    reply = generate_ai_reply(conv, inbound_message=inbound)

    assert reply.escalate is False
    assert "анекдот" in reply.text.lower() or "Hoocon" in reply.text
    actions = reply.payload_extra.get("chat_actions") or []
    assert [a["id"] for a in actions] == ["call_manager"]


@pytest.mark.django_db
def test_uncertain_reply_offers_branch_buttons(gigachat_on) -> None:
    """Неопределённый вопрос → кнопки «Позвать менеджера» / «Продолжить с ботом»."""
    from supportchat.gigachat.reply import generate_ai_reply

    conv = _conversation()
    inbound = _inbound(conv, "zxqwv непонятный запрос")

    reply = generate_ai_reply(conv, inbound_message=inbound)

    actions = reply.payload_extra.get("chat_actions") or []
    assert [a["id"] for a in actions] == ["call_manager", "continue_bot"]


@pytest.mark.django_db
def test_escalation_reply_carries_continue_button(gigachat_on) -> None:
    """На сообщении о передаче менеджеру есть путь назад к боту."""
    from supportchat.gigachat.reply import generate_ai_reply

    conv = _conversation()
    inbound = _inbound(conv, "позовите менеджера")

    reply = generate_ai_reply(conv, inbound_message=inbound)

    assert reply.escalate is True
    actions = reply.payload_extra.get("chat_actions") or []
    assert [a["id"] for a in actions] == ["continue_bot"]


@pytest.mark.django_db
def test_task_writes_chat_actions_into_message(gigachat_on) -> None:
    """gigachat_reply сохраняет кнопки в raw_payload → API отдаёт actions."""
    conv = _conversation()
    inbound, _ = add_inbound_message(conv, "zxqwv непонятный запрос")

    assert gigachat_reply(conv.pk, inbound.pk) == "ok"

    system = Message.objects.get(conversation=conv, direction=MessageDirection.SYSTEM)
    assert [a["id"] for a in system.raw_payload["chat_actions"]] == [
        "call_manager",
        "continue_bot",
    ]


@pytest.mark.django_db
def test_continue_bot_revives_escalated_conversation(gigachat_on) -> None:
    """«Продолжить с ботом» снимает эскалацию, пока менеджер не вступил."""
    conv = _conversation(
        ai_active=False,
        ai_escalated_at=timezone.now() - timedelta(minutes=10),
        ai_turn_count=5,
    )
    inbound = _inbound(conv, "Продолжить с ботом", raw_payload={"chat_action": "continue_bot"})

    assert gigachat_reply(conv.pk, inbound.pk) == "ok"

    conv.refresh_from_db()
    assert conv.ai_active is True
    assert conv.ai_escalated_at is None
    assert conv.ai_turn_count == 1  # reset + turn consumed by continue reply
    system = Message.objects.get(conversation=conv, direction=MessageDirection.SYSTEM)
    assert "продолжаем" in system.body.lower()


@pytest.mark.django_db
def test_continue_bot_ignored_when_manager_replied(gigachat_on, django_user_model) -> None:
    """Менеджер уже ответил после эскалации — бот не возвращается."""
    manager = django_user_model.objects.create_user(
        username="mgr-cont",
        email="mgr-cont@example.com",
        password="x",
        is_staff=True,
    )
    conv = _conversation(ai_active=False, ai_escalated_at=timezone.now() - timedelta(minutes=10))
    add_staff_reply(conv, "Я на связи", author=manager)
    inbound = _inbound(conv, "Продолжить с ботом", raw_payload={"chat_action": "continue_bot"})

    assert gigachat_reply(conv.pk, inbound.pk) == "notice"

    conv.refresh_from_db()
    assert conv.ai_active is False
    assert conv.ai_escalated_at is not None
    system = Message.objects.filter(
        conversation=conv,
        direction=MessageDirection.SYSTEM,
        raw_payload__ai_notice=True,
    ).first()
    assert system is not None
    assert "менеджер" in system.body.lower()


@pytest.mark.django_db
def test_busy_followup_offers_continue_with_bot(gigachat_on) -> None:
    """Busy-followup несёт кнопку возврата к боту."""
    from supportchat.tasks import support_escalation_busy_followup

    conv = _conversation(ai_active=False)
    Conversation.objects.filter(pk=conv.pk).update(
        ai_escalated_at=timezone.now() - timedelta(hours=1),
    )

    assert support_escalation_busy_followup(conv.pk) == "sent"

    msg = Message.objects.get(conversation=conv, direction=MessageDirection.SYSTEM)
    assert [a["id"] for a in msg.raw_payload["chat_actions"]] == ["continue_bot"]


@pytest.mark.django_db
def test_clarify_questions_differ_by_product_kind(gigachat_on) -> None:
    """Привод / комплект привод+кран / шаровой кран — разные вопросы."""
    from supportchat.gigachat.triage_product import triage_product_clarification_reply

    actuator = triage_product_clarification_reply("нужен привод на заслонку 0.5 м2")
    assert "заслонки" in actuator or "арматуры" in actuator
    assert "напряжение" in actuator
    assert "/catalog/komplekty" not in actuator

    kit = triage_product_clarification_reply("нужен комплект привод с краном")
    assert "кран + привод" in kit
    assert "DN" in kit and "напряжение привода" in kit
    assert "/catalog/komplekty" in kit

    ball = triage_product_clarification_reply("нужен шаровой кран DN25")
    assert "шаровой кран" in ball
    assert "DN" in ball and "PN" in ball
    assert "/catalog/sharovye-krany" in ball
    # Для крана без привода вопросы про напряжение не задаём.
    assert "напряжение" not in ball


@pytest.mark.django_db
def test_kit_intent_via_valve_and_actuator_words(gigachat_on) -> None:
    """«кран с приводом» без слова «комплект» — та же ветка комплекта."""
    from supportchat.gigachat.triage_product import triage_product_clarification_reply

    reply = triage_product_clarification_reply("подскажите шаровой кран с приводом 24В")
    assert "кран + привод" in reply


@pytest.mark.django_db
def test_fire_wins_over_kit_in_catalog_hint(gigachat_on) -> None:
    """Противопожарный комплект → огнестойкая категория, не /komplekty."""
    from supportchat.gigachat.triage_product import triage_product_clarification_reply

    reply = triage_product_clarification_reply("комплект привода для противопожарного клапана")
    assert "elektroprivody-protivopozharnye" in reply


@pytest.mark.django_db
def test_inbound_superseded_debounces_push() -> None:
    """Более новое inbound → старая debounce-задача пуша пропускается."""
    conv = _conversation()
    first = _inbound(conv, "Привет")
    assert inbound_superseded(conv.pk, first.pk) is False
    _inbound(conv, "Второе сообщение")
    assert inbound_superseded(conv.pk, first.pk) is True


@pytest.mark.django_db
def test_staff_push_task_skips_superseded(gigachat_on) -> None:
    """WebPush-задача не шлёт пуш, если за дебаунс пришло новое сообщение."""
    from webpush.tasks import notify_staff_support_inbound

    conv = _conversation()
    first = _inbound(conv, "Привет")
    newer = _inbound(conv, "Ау")

    assert notify_staff_support_inbound(conv.pk, first.pk) == 0
    # Последнее сообщение бёрста — отправляет.
    site = SiteSettings.load()
    site.staff_push_support_enabled = True
    site.save(update_fields=["staff_push_support_enabled"])
    assert notify_staff_support_inbound(conv.pk, newer.pk) == 0  # нет подписок — но не skip


@pytest.mark.django_db
def test_housekeeping_closes_stale_and_keeps_waiting(gigachat_on, django_user_model) -> None:
    """Sweep: неактивный диалог закрывается, эскалация без ответа остаётся."""
    old = timezone.now() - timedelta(hours=100)

    stale = _conversation()
    inbound = _inbound(stale, "Старый вопрос")
    Message.objects.filter(pk=inbound.pk).update(created_at=old)
    Conversation.objects.filter(pk=stale.pk).update(last_message_at=old)

    waiting = _conversation()
    inbound2 = _inbound(waiting, "Жду менеджера")
    Message.objects.filter(pk=inbound2.pk).update(created_at=old)
    Conversation.objects.filter(pk=waiting.pk).update(
        last_message_at=old,
        ai_active=False,
        ai_escalated_at=old,
        contact_email="guest@example.com",  # иначе sweep запланирует followup .delay()
    )

    stats = supportchat_housekeeping()

    stale.refresh_from_db()
    waiting.refresh_from_db()
    assert stale.status == ConversationStatus.CLOSED
    assert stale.messages.filter(raw_payload__auto_closed=True).exists()
    assert waiting.status == ConversationStatus.OPEN
    assert stats["auto_closed"] >= 1


@pytest.mark.django_db
def test_housekeeping_deletes_empty_sessions() -> None:
    """Пустые сессии старше TTL удаляются, свежие и непустые — нет."""
    old_empty = _conversation()
    Conversation.objects.filter(pk=old_empty.pk).update(
        created_at=timezone.now() - timedelta(hours=30),
    )
    fresh_empty = _conversation()
    with_messages = _conversation()
    _inbound(with_messages, "Вопрос")
    Conversation.objects.filter(pk=with_messages.pk).update(
        created_at=timezone.now() - timedelta(hours=30),
    )

    stats = supportchat_housekeeping()

    assert not Conversation.objects.filter(pk=old_empty.pk).exists()
    assert Conversation.objects.filter(pk=fresh_empty.pk).exists()
    assert Conversation.objects.filter(pk=with_messages.pk).exists()
    assert stats["empty_deleted"] >= 1


def _admin_filter(filter_cls, params: dict) -> object:
    """Instantiate a SimpleListFilter; params values are lists like request.GET."""
    from django.contrib import admin as django_admin

    model_admin = ConversationAdmin(Conversation, django_admin.site)
    list_params = {k: [v] for k, v in params.items()}
    return filter_cls(None, list_params, Conversation, model_admin)


@pytest.mark.django_db
def test_awaiting_manager_filter(django_user_model) -> None:
    """Фильтр показывает эскалированные диалоги без ответа менеджера."""
    manager = django_user_model.objects.create_user(
        username="mgr-flt",
        email="mgr-flt@example.com",
        password="x",
        is_staff=True,
    )
    waiting = _conversation(ai_escalated_at=timezone.now())
    answered = _conversation(ai_escalated_at=timezone.now() - timedelta(hours=1))
    add_staff_reply(answered, "Отвечаю", author=manager)
    plain = _conversation()

    flt = _admin_filter(AwaitingManagerFilter, {"awaiting_manager": "yes"})
    qs = flt.queryset(None, Conversation.objects.all())

    assert waiting in qs
    assert answered not in qs
    assert plain not in qs


@pytest.mark.django_db
def test_has_messages_filter() -> None:
    """Фильтр «сообщения» отделяет пустые сессии от диалогов."""
    from django.contrib import admin as django_admin

    model_admin = ConversationAdmin(Conversation, django_admin.site)
    with_messages = _conversation()
    _inbound(with_messages, "Вопрос")
    empty = _conversation()

    qs = model_admin.get_queryset(None)
    flt_yes = _admin_filter(HasMessagesFilter, {"has_messages": "yes"})
    flt_no = _admin_filter(HasMessagesFilter, {"has_messages": "no"})

    assert with_messages in flt_yes.queryset(None, qs)
    assert empty not in flt_yes.queryset(None, qs)
    assert empty in flt_no.queryset(None, qs)


@pytest.mark.django_db
def test_empty_conversations_sort_last() -> None:
    """Пустые сессии не должны всплывать выше диалогов (NULLS LAST)."""
    from django.contrib import admin as django_admin

    empty_new = _conversation()
    with_messages = _conversation()
    _inbound(with_messages, "Привет")

    model_admin = ConversationAdmin(Conversation, django_admin.site)
    ordered = list(model_admin.get_queryset(None))

    assert ordered[0].pk == with_messages.pk
    assert ordered[-1].pk == empty_new.pk


@pytest.mark.django_db
def test_reopen_closed_conversation_revives_bot(gigachat_on, django_user_model) -> None:
    """Клиент пишет в закрытый диалог → бот снова отвечает, assignee сброшен."""
    from unittest.mock import patch

    from supportchat.gigachat.reply import generate_ai_reply

    manager = django_user_model.objects.create_user(username="mgr-reopen", email="m@e.co", password="x", is_staff=True)
    conv = _conversation(
        status=ConversationStatus.CLOSED,
        ai_active=False,
        ai_escalated_at=timezone.now() - timedelta(days=2),
        assignee=manager,
        ai_turn_count=9,
    )
    inbound, _ = add_inbound_message(conv, "расскажи анекдот")

    conv.refresh_from_db()
    assert conv.status == ConversationStatus.OPEN
    assert conv.ai_active is True and conv.ai_escalated_at is None
    assert conv.assignee is None and conv.ai_turn_count == 0

    with patch("supportchat.gigachat.reply.chat_completion"):
        reply = generate_ai_reply(conv, inbound_message=inbound)
    assert reply.escalate is False


@pytest.mark.django_db
def test_stale_escalation_resumes_bot(gigachat_on) -> None:
    """Менеджер не ответил за окно протухания — бот подхватывает новый вопрос."""
    old = timezone.now() - timedelta(minutes=45)
    conv = _conversation()
    _inbound(conv, "позовите менеджера")
    Conversation.objects.filter(pk=conv.pk).update(
        ai_active=False,
        ai_escalated_at=old,
    )
    inbound = _inbound(conv, "а что с доставкой вообще zxqwv")

    result = gigachat_reply(conv.pk, inbound.pk)

    assert result == "ok"
    conv.refresh_from_db()
    assert conv.ai_active is True and conv.ai_escalated_at is None
    bodies = list(
        Message.objects.filter(conversation=conv, direction=MessageDirection.SYSTEM).values_list("body", flat=True)
    )
    assert any("продолжу помогать" in body for body in bodies)


@pytest.mark.django_db
def test_fresh_escalation_stays_silent(gigachat_on) -> None:
    """Эскалация 10 минут назад без ответа менеджера — бот ещё ждёт."""
    conv = _conversation()
    _inbound(conv, "позовите менеджера")
    Conversation.objects.filter(pk=conv.pk).update(
        ai_active=False,
        ai_escalated_at=timezone.now() - timedelta(minutes=10),
    )
    inbound = _inbound(conv, "ну и долго ждать?")

    assert gigachat_reply(conv.pk, inbound.pk) == "not_eligible"


@pytest.mark.django_db
def test_manager_thread_resumes_after_long_silence(gigachat_on, django_user_model) -> None:
    """Менеджер ответил и пропал — после долгой тишины бот возвращается."""
    manager = django_user_model.objects.create_user(username="mgr-stale", email="s@e.co", password="x", is_staff=True)
    conv = _conversation()
    old_inbound = _inbound(conv, "вопрос")
    Message.objects.filter(pk=old_inbound.pk).update(created_at=timezone.now() - timedelta(hours=30))
    add_staff_reply(conv, "Ответил тогда", author=manager)
    Message.objects.filter(conversation=conv, direction=MessageDirection.OUTBOUND).update(
        created_at=timezone.now() - timedelta(hours=29)
    )
    inbound = _inbound(conv, "zxqwv новый вопрос")

    assert gigachat_reply(conv.pk, inbound.pk) == "ok"
    conv.refresh_from_db()
    assert conv.ai_active is True and conv.assignee_id is None


@pytest.mark.django_db
def test_manager_thread_recent_stays_silent(gigachat_on, django_user_model) -> None:
    """Менеджер в живом диалоге — бот не лезет."""
    manager = django_user_model.objects.create_user(username="mgr-live", email="l@e.co", password="x", is_staff=True)
    conv = _conversation()
    _inbound(conv, "вопрос")
    add_staff_reply(conv, "Сейчас отвечу", author=manager)
    inbound = _inbound(conv, "хорошо жду")

    assert gigachat_reply(conv.pk, inbound.pk) == "not_eligible"
    conv.refresh_from_db()
    assert conv.assignee_id == manager.pk


@pytest.mark.django_db
def test_stale_resume_works_on_telegram_channel(gigachat_on, monkeypatch) -> None:
    """Та же логика для Telegram: бот возвращается и ответ уходит в TG."""
    sent: list[str] = []
    monkeypatch.setattr(
        "social.publishers.publish_telegram",
        lambda chat_id, text, **kw: sent.append(text) or _PubOk(),
    )

    conv = _conversation(channel=Channel.TELEGRAM, external_user_id="tg-77")
    _inbound(conv, "позовите менеджера")
    Conversation.objects.filter(pk=conv.pk).update(
        ai_active=False,
        ai_escalated_at=timezone.now() - timedelta(minutes=60),
    )
    inbound = _inbound(conv, "zxqwv вопрос")

    assert gigachat_reply(conv.pk, inbound.pk) == "ok"
    conv.refresh_from_db()
    assert conv.ai_active is True
    assert sent, "ответы должны уходить в Telegram"
    assert any("продолжу помогать" in html.unescape(t) for t in sent)


class _PubOk:
    ok = True
    error = None
    skipped = False
