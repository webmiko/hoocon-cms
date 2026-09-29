"""In-chat product quiz: engine, free-text parsing, catalog URL, pipeline."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from sitesettings.models import SiteSettings
from supportchat.models import Channel, Conversation, Message, MessageDirection
from supportchat.tasks import gigachat_reply


@pytest.fixture
def gigachat_on(settings, monkeypatch: pytest.MonkeyPatch) -> SiteSettings:
    settings.GIGACHAT_CREDENTIALS = "test-key"
    settings.GIGACHAT_MODE = "triage"
    site = SiteSettings.load()
    site.gigachat_enabled = True
    site.ai_max_turns = 30
    site.save(update_fields=["gigachat_enabled", "ai_max_turns"])
    monkeypatch.setattr("supportchat.services.is_open_now", lambda: True)
    return site


_seq = 0


def _conv() -> Conversation:
    global _seq  # noqa: PLW0603
    _seq += 1
    return Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id=f"quiz-{_seq}",
    )


def _inbound(conv: Conversation, body: str, chat_action: str | None = None) -> Message:
    payload = {"chat_action": chat_action} if chat_action else None
    return Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body=body,
        raw_payload=payload,
    )


def _send(conv: Conversation, body: str, chat_action: str | None = None) -> Message:
    """Inbound + sync AI task → the last system message (bot answer)."""
    inbound = _inbound(conv, body, chat_action)
    assert gigachat_reply(conv.pk, inbound.pk) == "ok"
    return Message.objects.filter(conversation=conv, direction=MessageDirection.SYSTEM).latest("id")


def _actions(msg: Message) -> list[str]:
    payload = msg.raw_payload or {}
    return [a["id"] for a in payload.get("chat_actions") or []]


def _step(msg: Message) -> str:
    return str((msg.raw_payload or {}).get("quiz_step", ""))


def _answers(msg: Message) -> dict:
    return (msg.raw_payload or {}).get("quiz_answers") or {}


# --- engine (pure functions) -------------------------------------------------


def test_next_step_actuator_general_path() -> None:
    from supportchat.gigachat import quiz_bot

    answers: dict[str, str] = {"need": "actuator", "application": "general"}
    assert quiz_bot.next_step(answers, "application") == "voltage"
    answers["voltage"] = "24"
    assert quiz_bot.next_step(answers, "voltage") == "control"
    answers["control"] = "onoff"
    assert quiz_bot.next_step(answers, "control") == "aux_switch"
    answers["aux_switch"] = "no"
    assert quiz_bot.next_step(answers, "aux_switch") == "damper_area"
    assert quiz_bot.next_step(answers, "damper_area") == "damper_type"
    assert quiz_bot.next_step(answers, "damper_type") == "damper_pressure"
    assert quiz_bot.next_step(answers, "damper_pressure") is None


def test_next_step_fire_asks_temp_sensor_skips_control() -> None:
    from supportchat.gigachat import quiz_bot

    answers = quiz_bot.apply_choice({"need": "actuator"}, "application", "fire")
    assert answers["control"] == "onoff"  # авто-лок, как в квизе
    assert quiz_bot.next_step(answers, "voltage") == "temp_sensor"
    assert quiz_bot.next_step(answers, "temp_sensor") == "damper_area"


def test_next_step_smoke_no_spring_skips_temp_sensor() -> None:
    from supportchat.gigachat import quiz_bot

    answers = quiz_bot.apply_choice({"need": "actuator"}, "application", "smoke")
    assert quiz_bot.next_step(answers, "application") == "smoke_return"
    answers = quiz_bot.apply_choice(answers, "smoke_return", "no_spring")
    assert answers["temp_sensor"] == "no"
    assert quiz_bot.next_step(answers, "smoke_return") == "voltage"
    assert quiz_bot.next_step(answers, "voltage") == "damper_area"


def test_next_step_failsafe_type_branch() -> None:
    from supportchat.gigachat import quiz_bot

    answers = quiz_bot.apply_choice({"need": "actuator"}, "application", "failsafe")
    assert quiz_bot.next_step(answers, "application") == "failsafe_type"
    answers = quiz_bot.apply_choice(answers, "failsafe_type", "electronic")
    assert quiz_bot.next_step(answers, "failsafe_type") == "voltage"


def test_next_step_kit_and_flanged_dn() -> None:
    from supportchat.gigachat import quiz_bot

    answers = quiz_bot.apply_choice({}, "need", "kit")
    assert quiz_bot.next_step(answers, "need") == "voltage"
    assert quiz_bot.next_step(answers, "voltage") == "control"
    assert quiz_bot.next_step(answers, "control") == "aux_switch"
    assert quiz_bot.next_step(answers, "aux_switch") == "dn"
    # Фланцевый DN65 → ways/kvs авто-лок, как на фронте.
    answers = quiz_bot.apply_choice(answers, "dn", "65")
    assert answers["ways"] == "2" and answers["kvs"] == "over_40"
    assert quiz_bot.next_step(answers, "dn") is None
    # Муфтовый DN25 → спрашиваем kvs и ходы.
    answers = quiz_bot.apply_choice(answers, "dn", "25")
    assert "ways" not in answers and "kvs" not in answers
    assert quiz_bot.next_step(answers, "dn") == "kvs"
    assert quiz_bot.next_step(answers, "kvs") == "ways"
    assert quiz_bot.next_step(answers, "ways") is None


def test_next_step_adapter_and_ball_valve() -> None:
    from supportchat.gigachat import quiz_bot

    adapter = quiz_bot.apply_choice({}, "need", "adapter")
    assert quiz_bot.next_step(adapter, "need") == "adapter_type"
    assert quiz_bot.next_step(adapter, "adapter_type") is None

    ball = quiz_bot.apply_choice({}, "need", "ball_valve")
    assert quiz_bot.next_step(ball, "need") == "dn"


def test_moment_estimate_matches_frontend_formula() -> None:
    """M = S×P×Kтип×Kзапас/100 с округлением в лестницу Hoocon."""
    from supportchat.gigachat import quiz_bot

    # 0.3 м² · 450 Па · 1.4 · 1.3 / 100 = 2.46 → ближайший шаг 4 Нм.
    assert (
        quiz_bot.estimate_moment_nm(
            {"damper_area": "up_to_0_3", "damper_pressure": "medium", "damper_type": "rectangular"}
        )
        == 4
    )
    # Большая заслонка, высокое давление, шибер → запас 1.4, кап лестницы 40.
    assert (
        quiz_bot.estimate_moment_nm({"damper_area": "over_4", "damper_pressure": "very_high", "damper_type": "gate"})
        == 40
    )
    # «Не знаю» по площади → оценки нет.
    assert quiz_bot.estimate_moment_nm({"damper_area": "skip"}) is None


# --- free-text parsing -------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "text", "expected"),
    [
        ("voltage", "24 вольта от щита", "24"),
        ("voltage", "230", "230"),
        ("control", "просто открыть-закрыть", "onoff"),
        ("control", "плавное регулирование", "modulating"),
        ("control", "0-10 в", "modulating"),
        ("dn", "DN25", "25"),
        ("dn", "диаметр 32", "32"),
        ("ways", "трехходовой", "3"),
        ("ways", "2-ходовой", "2"),
        ("damper_area", "около 2 квадратов", "1_6_2_5"),
        ("damper_area", "0,5 м2", "0_3_0_6"),
        ("damper_type", "круглая заслонка", "round"),
        ("damper_type", "шиберная", "gate"),
        ("damper_pressure", "500 па", "medium"),
        ("damper_pressure", "1500", "very_high"),
        ("aux_switch", "да, нужны контакты", "yes"),
        ("temp_sensor", "нет", "no"),
        ("application", "противопожарный клапан", "fire"),
        ("application", "на дымоудаление", "smoke"),
        ("failsafe_type", "электронный", "electronic"),
        ("smoke_return", "без пружины", "no_spring"),
        ("adapter_type", "br-ml", "br_ml"),
        ("need", "нужен шаровой кран", "ball_valve"),
        ("need", "комплект кран с приводом", "kit"),
        ("need", "кронштейн", "adapter"),
    ],
)
def test_parse_step_answer_free_text(step: str, text: str, expected: str) -> None:
    from supportchat.gigachat import quiz_bot

    assert quiz_bot.parse_step_answer(step, text) == expected


def test_parse_skip_on_dont_know() -> None:
    from supportchat.gigachat import quiz_bot

    assert quiz_bot.parse_step_answer("voltage", "пока не знаю") == "skip"
    # Нескипаемый шаг «need» не принимает «не знаю».
    assert quiz_bot.parse_step_answer("need", "не знаю") is None


# --- catalog URL -------------------------------------------------------------


def _fake_facets(category: str) -> dict[str, list[str]]:
    return {
        "voltage": ["24 V AC/DC", "230 V AC"],
        "control": ["открыто/закрыто", "пропорциональное (0–10 В)"],
        "moment": ["4 Н·м", "10 Н·м", "20 Н·м"],
        "area": ["до 0,5 м²", "до 1,0 м²"],
        "aux_switch": ["SPDT-1", "SPDT-2", "Нет"],
        "temp_sensor": ["SAF72", "Нет"],
        "dn": ["DN15", "DN20", "DN25", "DN65"],
        "ways": ["2-ходовой", "3-ходовой"],
        "kvs": ["2,5", "6,3", "16", "40", "63"],
    }


def test_catalog_url_kit_with_facets(monkeypatch: pytest.MonkeyPatch) -> None:
    from supportchat.gigachat import quiz_bot

    monkeypatch.setattr(quiz_bot, "_category_facets", _fake_facets)
    url = quiz_bot.quiz_catalog_url(
        {
            "need": "kit",
            "voltage": "24",
            "control": "onoff",
            "aux_switch": "yes",
            "dn": "25",
            "kvs": "2_5_to_6",
            "ways": "3",
        }
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert parsed.path == "/catalog/komplekty"
    assert params["voltage"] == ["24 V AC/DC"]
    assert params["dn"] == ["DN25"]
    assert params["ways"] == ["3-ходовой"]
    assert params["aux_switch"] == ["SPDT-2"]  # как на фронте: yes → SPDT-2


def test_catalog_url_actuator_fire_category_and_moment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from supportchat.gigachat import quiz_bot

    monkeypatch.setattr(quiz_bot, "_category_facets", _fake_facets)
    url = quiz_bot.quiz_catalog_url(
        {
            "need": "actuator",
            "application": "fire",
            "control": "onoff",
            "voltage": "230",
            "temp_sensor": "yes",
            "damper_area": "0_6_1_0",
            "damper_type": "rectangular",
            "damper_pressure": "medium",
        }
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert parsed.path == "/catalog/elektroprivody-protivopozharnye-i-dymovye"
    assert params["voltage"] == ["230 V AC"]
    assert params["temp_sensor"] == ["SAF72"]
    # 1.0 м² · 450 · 1.4 · 1.3 / 100 = 8.19 → лестница → 10 Нм.
    assert params["moment"] == ["10 Н·м"]
    # Fire/smoke: control зафиксирован, но в URL не уходит (на фронте тоже skip).
    assert "control" not in params


def test_catalog_url_smoke_q_and_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from supportchat.gigachat import quiz_bot

    monkeypatch.setattr(quiz_bot, "_category_facets", _fake_facets)
    smoke = quiz_bot.quiz_catalog_url({"need": "actuator", "application": "smoke", "smoke_return": "spring"})
    parsed = urlparse(smoke)
    assert parsed.path == "/catalog/elektroprivody-dlya-klapanov-dymoudaleniya"
    assert parse_qs(parsed.query)["q"] == ["HVD"]

    adapter = quiz_bot.quiz_catalog_url({"need": "adapter", "adapter_type": "br_ml"})
    assert urlparse(adapter).path == "/catalog/adaptery"
    assert parse_qs(urlparse(adapter).query)["q"] == ["BR-ML"]


# --- end-to-end flow ---------------------------------------------------------


@pytest.mark.django_db
def test_product_intent_offers_quiz(gigachat_on) -> None:
    """Продуктовый вопрос → оффер подбора в чате с кнопкой квиза."""
    conv = _conv()
    msg = _send(conv, "подберите привод на заслонку")

    assert (msg.raw_payload or {}).get("quiz_offer") is True
    ids = _actions(msg)
    assert "quiz:start" in ids and "call_manager" in ids


@pytest.mark.django_db
def test_quiz_full_flow_via_buttons(gigachat_on) -> None:
    """Старт → вопросы → результат с ссылкой на каталог."""
    conv = _conv()
    _inbound(conv, "нужен шаровой кран")
    msg = _send(conv, "Подобрать в чате", chat_action="quiz:start")
    # «need» угадан из предыдущего сообщения → сразу DN.
    assert _step(msg) == "dn"
    assert _answers(msg)["need"] == "ball_valve"
    assert any(a == "quiz:dn:25" for a in _actions(msg))

    msg = _send(conv, "DN 25", chat_action="quiz:dn:25")
    assert _step(msg) == "kvs"

    msg = _send(conv, "Пока не знаю", chat_action="quiz:kvs:skip")
    assert _step(msg) == "ways"

    msg = _send(conv, "3-ходовой", chat_action="quiz:ways:3")
    assert _step(msg) == ""
    assert (msg.raw_payload or {}).get("quiz_done") is True
    assert "/catalog/sharovye-krany" in msg.body
    assert "dn=DN25" not in msg.body  # фасетов может не быть — но путь верный
    assert _answers(msg)["dn"] == "25"


@pytest.mark.django_db
def test_quiz_free_text_answers(gigachat_on) -> None:
    """Ответы текстом без кнопок продвигают квиз."""
    conv = _conv()
    _inbound(conv, "нужен привод")
    msg = _send(conv, "Подобрать в чате", chat_action="quiz:start")
    assert _step(msg) == "application"

    msg = _send(conv, "обычная вентиляция")
    assert _step(msg) == "voltage"

    msg = _send(conv, "24 вольта")
    assert _step(msg) == "control"

    msg = _send(conv, "плавное регулирование")
    assert _step(msg) == "aux_switch"


@pytest.mark.django_db
def test_quiz_reask_then_park(gigachat_on) -> None:
    """Непонятный ответ → переспрос; второй раз — обычный пайплайн."""
    conv = _conv()
    _inbound(conv, "нужен привод")
    _send(conv, "Подобрать в чате", chat_action="quiz:start")

    msg = _send(conv, "абракадабра совсем непонятная")
    assert _step(msg) == "application"  # переспросил тот же шаг

    msg = _send(conv, "ещё больше абракадабры zxqwv")
    # Квиз припаркован: последнее системное сообщение уже не quiz_step.
    assert _step(msg) == ""
    assert (msg.raw_payload or {}).get("quiz_step") is None


@pytest.mark.django_db
def test_quiz_typed_start_after_offer(gigachat_on) -> None:
    """Канал без кнопок: «давай» после оффера запускает квиз."""
    conv = _conv()
    msg = _send(conv, "подберите привод")
    assert (msg.raw_payload or {}).get("quiz_offer") is True

    msg = _send(conv, "давай подберём")
    assert _step(msg) == "application"  # need угадан → application


@pytest.mark.django_db
def test_quiz_stale_button_reasks_current(gigachat_on) -> None:
    """Клик по кнопке старого шага не ломает состояние."""
    conv = _conv()
    _inbound(conv, "нужен привод")
    _send(conv, "Подобрать в чате", chat_action="quiz:start")
    _send(conv, "обычная вентиляция")

    msg = _send(conv, "ОЗК", chat_action="quiz:application:fire")
    # Шаг уже не application — бот переспросил актуальный (voltage).
    assert _step(msg) == "voltage"


@pytest.mark.django_db
def test_manager_handoff_interrupts_quiz(gigachat_on) -> None:
    """«Позовите менеджера» посреди квиза — обычная эскалация."""
    conv = _conv()
    _inbound(conv, "нужен привод")
    _send(conv, "Подобрать в чате", chat_action="quiz:start")

    inbound = _inbound(conv, "лучше позовите менеджера")
    assert gigachat_reply(conv.pk, inbound.pk).startswith("escalated")
    conv.refresh_from_db()
    assert conv.ai_active is False


# --- serializer --------------------------------------------------------------


def test_chat_action_accepts_quiz_ids() -> None:
    from supportchat.serializers import MessageCreateSerializer

    ok = MessageCreateSerializer(data={"body": "x", "chat_action": "quiz:voltage:24"})
    assert ok.is_valid(), ok.errors
    bad = MessageCreateSerializer(data={"body": "x", "chat_action": "rm -rf /"})
    assert not bad.is_valid()
