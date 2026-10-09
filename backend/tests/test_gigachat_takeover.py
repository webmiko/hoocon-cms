"""Bot takeover when a manager stays silent after a client message."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from sitesettings.models import SiteSettings
from supportchat.gigachat.busy_followup import escalation_busy_followup_seconds
from supportchat.gigachat.manager_silence import (
    escalation_takeover_seconds,
    manager_reply_timeout_seconds,
)
from supportchat.gigachat.triage import gigachat_mode, is_triage_mode
from supportchat.models import (
    Channel,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
)
from supportchat.services import add_inbound_message, add_staff_reply
from supportchat.tasks import support_manager_silence_watchdog


@pytest.fixture
def gigachat_on(settings, monkeypatch: pytest.MonkeyPatch) -> SiteSettings:
    settings.GIGACHAT_CREDENTIALS = "test-key"
    site = SiteSettings.load()
    site.gigachat_enabled = True
    site.gigachat_model = "GigaChat-2"
    site.save(update_fields=["gigachat_enabled", "gigachat_model"])
    monkeypatch.setattr("supportchat.services.is_open_now", lambda: True)
    return site


def _escalated_conversation(*, ago: timedelta = timedelta(0)) -> Conversation:
    return Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="takeover",
        ai_active=False,
        ai_escalated_at=timezone.now() - ago,
    )


def _stale_escalation() -> Conversation:
    """Handoff nobody picked up for longer than the takeover window."""
    return _escalated_conversation(ago=timedelta(seconds=escalation_takeover_seconds() + 60))


@pytest.mark.django_db(transaction=True)
def test_inbound_schedules_watchdog_when_manager_owned(
    gigachat_on, django_user_model, django_capture_on_commit_callbacks
) -> None:
    """Менеджер вёл диалог и замолчал — watchdog через окно ответа (45 с)."""
    staff = django_user_model.objects.create_user(username="owner", is_staff=True)
    conv = _escalated_conversation()
    conv.assignee = staff
    conv.save(update_fields=["assignee"])
    with django_capture_on_commit_callbacks(execute=True):
        with patch("supportchat.tasks.support_manager_silence_watchdog.apply_async") as enqueue:
            add_inbound_message(conv, "А привод DA2MU24 в наличии?")

    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs["countdown"] == 45
    assert enqueue.call_args.kwargs["args"][0] == conv.pk


@pytest.mark.django_db(transaction=True)
def test_inbound_on_fresh_handoff_waits_for_human(gigachat_on, django_capture_on_commit_callbacks) -> None:
    """M24: свежая передача менеджеру — watchdog не раньше окна эскалации."""
    conv = _escalated_conversation()
    with django_capture_on_commit_callbacks(execute=True):
        with patch("supportchat.tasks.support_manager_silence_watchdog.apply_async") as enqueue:
            add_inbound_message(conv, "А привод DA2MU24 в наличии?")

    enqueue.assert_called_once()
    countdown = enqueue.call_args.kwargs["countdown"]
    assert countdown > escalation_busy_followup_seconds()
    assert countdown >= escalation_takeover_seconds() - 5


def test_takeover_window_outlasts_busy_followup(settings) -> None:
    """M24: «менеджеры заняты» всегда раньше возврата бота, даже при коротком stale."""
    settings.SUPPORT_AI_RESUME_STALE_MINUTES = 1
    settings.SUPPORT_ESCALATION_BUSY_FOLLOWUP_SECONDS = 300
    assert escalation_takeover_seconds() > escalation_busy_followup_seconds()


@pytest.mark.django_db
def test_watchdog_does_not_take_fresh_handoff(gigachat_on) -> None:
    """M24: через 45 с после передачи менеджеру бот не забирает чат обратно."""
    conv = _escalated_conversation(ago=timedelta(seconds=manager_reply_timeout_seconds() + 5))
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен менеджер",
    )

    with patch("supportchat.tasks.gigachat_reply.delay") as reply_delay:
        result = support_manager_silence_watchdog(conv.pk, inbound.pk)

    assert result == "escalation_waiting"
    reply_delay.assert_not_called()
    conv.refresh_from_db()
    assert conv.ai_active is False
    assert conv.ai_escalated_at is not None


@pytest.mark.django_db
def test_gigachat_outage_escalation_does_not_loop(gigachat_on, django_capture_on_commit_callbacks) -> None:
    """M24: GigaChat недоступен → эскалация не возвращается боту через минуту.

    Раньше watchdog через 45 с снимал эскалацию, бот снова падал и клиент
    получал «бот недоступен» / «бот вернулся» по кругу.
    """
    from supportchat.gigachat.client import GigachatError
    from supportchat.tasks import gigachat_reply

    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="down-loop")
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Подскажите по приводу",
    )
    with (
        patch("supportchat.gigachat.reply.generate_ai_reply", side_effect=GigachatError("down")),
        patch("supportchat.tasks.support_manager_silence_watchdog.apply_async") as enqueue,
        patch("supportchat.tasks.support_escalation_busy_followup.apply_async"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        gigachat_reply.push_request(retries=gigachat_reply.max_retries)
        try:
            gigachat_reply.run(conv.pk, inbound.pk)
        finally:
            gigachat_reply.pop_request()

    assert enqueue.call_args.kwargs["countdown"] > escalation_busy_followup_seconds()
    assert support_manager_silence_watchdog(conv.pk, inbound.pk) == "escalation_waiting"


@pytest.mark.django_db(transaction=True)
def test_escalation_schedules_watchdog(gigachat_on, django_capture_on_commit_callbacks) -> None:
    """Эскалация ставит watchdog даже без новых входящих — бот вернётся сам."""
    from supportchat.tasks import _escalate_conversation

    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="esc-watch")
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен менеджер",
    )

    with django_capture_on_commit_callbacks(execute=True):
        with patch("supportchat.tasks.support_manager_silence_watchdog.apply_async") as enqueue:
            _escalate_conversation(conv, reason="test", post_handoff=False)

    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs["args"] == [conv.pk, inbound.pk]


@pytest.mark.django_db
def test_watchdog_takeover_skips_reply_when_already_answered(gigachat_on) -> None:
    """Вопрос уже отвечен ботом до эскалации — повторный ответ не нужен."""
    conv = _stale_escalation()
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Цена?",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.SYSTEM,
        body="Передал менеджеру.",
        raw_payload={"ai": True},
    )

    with patch("supportchat.tasks.gigachat_reply.delay") as reply_delay:
        result = support_manager_silence_watchdog(conv.pk, inbound.pk)

    assert result == "resumed"
    reply_delay.assert_not_called()
    assert Message.objects.filter(conversation=conv, raw_payload__ai_notice=True).exists()


@pytest.mark.django_db
def test_inbound_no_watchdog_when_bot_owns(gigachat_on) -> None:
    """Пока бот сам ведёт диалог — watchdog не нужен, отвечает gigachat_reply."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="bot-owned")
    with patch("supportchat.tasks.support_manager_silence_watchdog.apply_async") as enqueue:
        add_inbound_message(conv, "Привет")
        enqueue.assert_not_called()


@pytest.mark.django_db
def test_watchdog_resumes_ai_when_manager_silent(gigachat_on, django_user_model) -> None:
    """Менеджер молчит — бот снимает эскалацию/ассайни и отвечает клиенту."""
    staff = django_user_model.objects.create_user(username="mgr", is_staff=True)
    conv = _escalated_conversation()
    conv.assignee = staff
    conv.save(update_fields=["assignee"])
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Жду ответа",
    )

    with patch("supportchat.tasks.gigachat_reply.delay") as reply_delay:
        result = support_manager_silence_watchdog(conv.pk, inbound.pk)

    assert result == "resumed"
    conv.refresh_from_db()
    assert conv.ai_active is True
    assert conv.ai_escalated_at is None
    assert conv.assignee_id is None
    notice = Message.objects.filter(conversation=conv, raw_payload__ai_notice=True).first()
    assert notice is not None
    assert "менеджер" in notice.body.lower()
    reply_delay.assert_called_once_with(conv.pk, inbound.pk)


@pytest.mark.django_db
def test_watchdog_takeover_answers_latest_inbound(gigachat_on) -> None:
    """Серия сообщений клиента — ответ один, по последнему входящему."""
    conv = _stale_escalation()
    first = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужна заслонка",
    )
    latest = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Дымовая, 230 В",
    )

    with patch("supportchat.tasks.gigachat_reply.delay") as reply_delay:
        result = support_manager_silence_watchdog(conv.pk, first.pk)

    assert result == "resumed"
    reply_delay.assert_called_once_with(conv.pk, latest.pk)


@pytest.mark.django_db
def test_watchdog_skips_when_manager_replied(gigachat_on, django_user_model) -> None:
    """Менеджер успел ответить за окно тишины — бот не вмешивается."""
    staff = django_user_model.objects.create_user(username="mgr2", is_staff=True)
    conv = _escalated_conversation()
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Есть вопрос по монтажу",
    )
    add_staff_reply(conv, "Отвечаю — гляну чертёж.", author=staff)

    result = support_manager_silence_watchdog(conv.pk, inbound.pk)

    assert result == "manager_replied"
    conv.refresh_from_db()
    assert conv.ai_active is False
    assert conv.ai_escalated_at is not None


@pytest.mark.django_db
def test_watchdog_skips_when_already_ai(gigachat_on) -> None:
    """Бот уже ведёт диалог — повторный подхват не нужен."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="ai-owned")
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Привет",
    )

    result = support_manager_silence_watchdog(conv.pk, inbound.pk)

    assert result == "already_ai"
    assert not Message.objects.filter(conversation=conv, raw_payload__ai_notice=True).exists()


@pytest.mark.django_db
def test_watchdog_skips_closed(gigachat_on) -> None:
    conv = _escalated_conversation()
    conv.status = ConversationStatus.CLOSED
    conv.save(update_fields=["status"])
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="?",
    )

    assert support_manager_silence_watchdog(conv.pk, inbound.pk) == "closed"


@pytest.mark.django_db
def test_watchdog_disabled_without_gigachat(settings) -> None:
    settings.GIGACHAT_CREDENTIALS = "test-key"
    site = SiteSettings.load()
    site.gigachat_enabled = False
    site.save(update_fields=["gigachat_enabled"])
    conv = _escalated_conversation()
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Алло",
    )

    assert support_manager_silence_watchdog(conv.pk, inbound.pk) == "disabled"


def test_manager_reply_timeout_default_under_minute(settings) -> None:
    """Таймаут молчания по умолчанию — меньше минуты (без больших зависаний)."""
    assert manager_reply_timeout_seconds() < 60


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("reply", "user_texts", "blocked"),
    [
        # Просят пружинный возврат — артикул MU (без пружины) запрещён.
        ("Подойдёт DA6MU230-D/DS.", ["нужен привод с пружинным возвратом"], True),
        ("Подойдёт HVD-6MU230-S/ST.", ["нужен привод с пружинным возвратом"], True),
        ("Подойдёт DA10FU230-D/DS.", ["нужен привод с пружинным возвратом"], False),
        # Легитимный ответ с обоими вариантами не блокируем.
        ("Без пружины DA6MU230, с пружиной DA10FU230.", ["нужен пружинный возврат"], False),
        # Напряжение из суффикса: 230 при запросе 24 и наоборот.
        ("Ставьте DA10FU230-D/DS.", ["питание 24 вольта"], True),
        ("Ставьте DA10FU24-A/AS.", ["питание 230 В"], True),
        # Артикул, которого нет в базе знаний — галлюцинация.
        ("Подойдёт DA99FU999-X.", ["нужна заслонка"], True),
        # Внутренние пути репозитория и внешние ссылки.
        ("См. /_manuals-ru/DA/fu.html", ["паспорт"], True),
        ("См. https://belimo.com/x", ["аналог"], True),
        # Нормальный ответ по базе.
        ("Документация: /dokumentaciya?q=DA10FU230. Каталог /catalog.", ["нужна заслонка"], False),
    ],
)
def test_full_output_guard(reply: str, user_texts: list[str], blocked: bool) -> None:
    """Гвард full-режима: артикул из базы и соответствует требованиям клиента."""
    from supportchat.gigachat.triage_guard import full_output_blocked

    assert full_output_blocked(reply, user_texts=user_texts) is blocked


@pytest.mark.django_db
def test_ai_mode_site_settings_override(settings) -> None:
    """SiteSettings.ai_mode переопределяет GIGACHAT_MODE из env."""
    settings.GIGACHAT_MODE = "triage"
    site = SiteSettings.load()

    site.ai_mode = "full"
    site.save(update_fields=["ai_mode"])
    assert gigachat_mode() == "full"
    assert is_triage_mode() is False

    site.ai_mode = "triage"
    site.save(update_fields=["ai_mode"])
    assert gigachat_mode() == "triage"

    site.ai_mode = ""
    site.save(update_fields=["ai_mode"])
    assert gigachat_mode() == "triage"


@pytest.mark.django_db
def test_gigachat_failure_escalates_after_retries(gigachat_on) -> None:
    """GigaChat недоступен после ретраев → статус клиенту + эскалация на людей."""

    from supportchat.gigachat.client import GigachatError
    from supportchat.tasks import gigachat_reply

    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="down")
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Подскажите по приводу",
    )

    with patch("supportchat.gigachat.reply.generate_ai_reply") as gen:
        gen.side_effect = GigachatError("API недоступен")
        gigachat_reply.push_request(retries=gigachat_reply.max_retries)
        try:
            result = gigachat_reply.run(conv.pk, inbound.pk)
        finally:
            gigachat_reply.pop_request()

    assert result == "escalated:gigachat_error"
    conv.refresh_from_db()
    assert conv.ai_escalated_at is not None
    assert conv.ai_active is False
    notice = Message.objects.filter(conversation=conv, raw_payload__ai_notice=True).first()
    assert notice is not None
    assert "менеджер" in notice.body.lower()


@pytest.mark.django_db
def test_gigachat_failure_retries_before_final(gigachat_on) -> None:
    """Первый сбой GigaChat — ретрай таски, без эскалации."""
    from supportchat.gigachat.client import GigachatError
    from supportchat.tasks import gigachat_reply

    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="down2")
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Вопрос",
    )

    with patch("supportchat.gigachat.reply.generate_ai_reply") as gen, pytest.raises(GigachatError):
        # Вне воркера self.retry рейзит исходное исключение.
        gen.side_effect = GigachatError("timeout")
        gigachat_reply(conv.pk, inbound.pk)

    conv.refresh_from_db()
    assert conv.ai_escalated_at is None


@pytest.mark.django_db
def test_stale_takeover_still_resets_turn_count(gigachat_on) -> None:
    """Давняя тишина (>SUPPORT_AI_RESUME_MANAGER_HOURS) → resume с обнулением ходов."""
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="stale",
        ai_active=False,
        ai_turn_count=9,
        last_message_at=timezone.now() - timedelta(hours=25),
    )
    old = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.OUTBOUND,
        body="старый ответ",
    )
    # auto_now_add игнорирует created_at при create — бэкдатируем через update.
    Message.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Снова вопрос",
    )

    from supportchat.tasks import _resume_stale_ai

    assert _resume_stale_ai(conv, inbound) is True
    conv.refresh_from_db()
    assert conv.ai_turn_count == 0
