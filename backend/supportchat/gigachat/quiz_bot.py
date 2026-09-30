"""In-chat product picker — port of the site quiz (ProductPickerQuiz).

State lives on the last quiz SYSTEM message (``raw_payload.quiz_step`` /
``quiz_answers``) — no schema change, transcript is the source of truth.
Answers arrive as ``chat_action = "quiz:<step>:<choice>"`` button clicks or
as free text parsed per step. Results message carries the same catalog URL
the on-site quiz produces (category + facet query params).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from supportchat.models import Conversation, Message

from supportchat.gigachat.chat_actions import inbound_chat_action

QUIZ_ACTION_PREFIX = "quiz:"
QUIZ_START_ACTION = "quiz:start"
QUIZ_RESTART_ACTION = "quiz:restart"

_SKIP_LABEL = "Пока не знаю"

# step -> (question, [(choice_id, button label)], skippable)
_STEPS: dict[str, tuple[str, list[tuple[str, str]], bool]] = {
    "need": (
        "Что вам нужно?",
        [
            ("actuator", "Привод на заслонку / клапан"),
            ("ball_valve", "Шаровой кран"),
            ("kit", "Комплект кран + привод"),
            ("adapter", "Кронштейн на кран (BR-M / BR-ML)"),
        ],
        False,
    ),
    "application": (
        "Где будет работать привод?",
        [
            ("general", "Обычная вентиляция / кондиционирование"),
            ("fire", "Огнезадерживающий клапан (ОЗК)"),
            ("smoke", "Дымоудаление"),
            ("failsafe", "Возврат при отключении питания"),
            ("fast", "Быстрый ход заслонки"),
        ],
        False,
    ),
    "failsafe_type": (
        "Какой тип возврата при пропадании питания?",
        [
            ("spring", "Пружинный возврат (FU)"),
            ("electronic", "Электронный fail-safe (QX)"),
        ],
        False,
    ),
    "smoke_return": (
        "Нужен пружинный возврат на дымовом клапане?",
        [
            ("no_spring", "Без пружины (SA…MU)"),
            ("spring", "С пружиной (HVD-…F)"),
        ],
        True,
    ),
    "voltage": (
        "Какое питание?",
        [
            ("24", "24 В от щита"),
            ("230", "230 В от сети"),
        ],
        True,
    ),
    "control": (
        "Какое управление нужно?",
        [
            ("onoff", "Открыть / закрыть"),
            ("modulating", "Плавное регулирование (0–10 В)"),
        ],
        True,
    ),
    "aux_switch": (
        "Нужны сухие контакты положения в щит (сигнализация в BMS)?",
        [
            ("yes", "Да, нужны"),
            ("no", "Нет"),
        ],
        True,
    ),
    "temp_sensor": (
        "Нужен термодатчик SAF72 (~72 °C) по паспорту клапана?",
        [
            ("yes", "Да, нужен SAF72"),
            ("no", "Нет, без термодатчика"),
        ],
        True,
    ),
    "damper_area": (
        "Какая площадь прохода заслонки, м²?",
        [
            ("up_to_0_3", "До 0,3 м²"),
            ("0_3_0_6", "0,3–0,6 м²"),
            ("0_6_1_0", "0,6–1,0 м²"),
            ("1_0_1_6", "1,0–1,6 м²"),
            ("1_6_2_5", "1,6–2,5 м²"),
            ("2_5_4_0", "2,5–4,0 м²"),
            ("over_4", "Больше 4 м²"),
        ],
        True,
    ),
    "damper_type": (
        "Какой тип заслонки?",
        [
            ("round", "Круглая"),
            ("rectangular", "Прямоугольная"),
            ("gate", "Шиберная / ножевая"),
        ],
        True,
    ),
    "damper_pressure": (
        "Какое расчётное давление на заслонку, Па?",
        [
            ("low", "До 300 Па"),
            ("medium", "300–600 Па"),
            ("high", "600–1000 Па"),
            ("very_high", "Больше 1000 Па"),
        ],
        True,
    ),
    "dn": (
        "Условный проход DN?",
        [
            ("15", "DN 15"),
            ("20", "DN 20"),
            ("25", "DN 25"),
            ("32", "DN 32"),
            ("40", "DN 40"),
            ("50", "DN 50"),
            ("65", "DN 65"),
            ("80", "DN 80"),
            ("100", "DN 100"),
            ("125", "DN 125"),
            ("150", "DN 150"),
        ],
        True,
    ),
    "kvs": (
        "Какая нужна пропускная способность Kvs, м³/ч?",
        [
            ("up_to_2_5", "До 2,5"),
            ("2_5_to_6", "2,5–6,3"),
            ("6_to_16", "6–16"),
            ("16_to_40", "16–40"),
            ("over_40", "Больше 40"),
        ],
        True,
    ),
    "ways": (
        "Сколько ходов у крана?",
        [
            ("2", "2-ходовой"),
            ("3", "3-ходовой"),
        ],
        True,
    ),
    "adapter_type": (
        "Какой у вас привод Hoocon?",
        [
            ("br_m", "Без пружины (MU / MQU) → BR-M"),
            ("br_ml", "С пружиной (FU) → BR-ML"),
        ],
        True,
    ),
}

_STEP_FIELD: dict[str, str] = {
    "need": "need",
    "application": "application",
    "failsafe_type": "failsafe_type",
    "smoke_return": "smoke_return",
    "voltage": "voltage",
    "control": "control",
    "aux_switch": "aux_switch",
    "temp_sensor": "temp_sensor",
    "damper_area": "damper_area",
    "damper_type": "damper_type",
    "damper_pressure": "damper_pressure",
    "dn": "dn",
    "kvs": "kvs",
    "ways": "ways",
    "adapter_type": "adapter_type",
}

# DN65–150 — фланцевые 8100Q/H8103: только 2-ходовые, один Kvs на DN.
_FLANGED_DNS = frozenset({"65", "80", "100", "125", "150"})

_QUIZ_OFFER_TEXT = (
    "Могу подобрать прямо здесь — задам несколько вопросов и дам ссылку "
    "на готовую подборку в каталоге. Нажмите «Подобрать в чате» или просто "
    "напишите «подбор». Либо откройте квиз на главной /#podbor."
)
_QUIZ_REASK_TEXT = (
    "Не совсем понял ответ — выберите вариант кнопкой или ответьте коротко "
    "(например, «24 В» или «DN 25»). Если хотите другое — напишите вопрос."
)
_QUIZ_START_TEXT_RE = re.compile(r"подобр|подбор|давай|начн|^\s*да\b", re.IGNORECASE)

_CATEGORY = {
    "ball_valve": "sharovye-krany",
    "kit": "komplekty",
    "adapter": "adaptery",
    "fire": "elektroprivody-protivopozharnye-i-dymovye",
    "smoke": "elektroprivody-dlya-klapanov-dymoudaleniya",
    "fast": "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    "spring": "elektroprivody-s-pruzhinnym-vozvratom",
    "electronic": "elektronnye-otkazoustoychivye-vozdushnye-privody",
    "general": "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
}

# --- engine (port of quizEngine.ts) ----------------------------------------


def _is_flanged_dn(dn: str | None) -> bool:
    return bool(dn) and dn != "skip" and dn in _FLANGED_DNS


def _needs_sizing(answers: dict[str, str]) -> bool:
    if answers.get("need") not in ("ball_valve", "kit"):
        return False
    return not _is_flanged_dn(answers.get("dn"))


def _needs_temp_sensor(answers: dict[str, str]) -> bool:
    if answers.get("need") != "actuator":
        return False
    if answers.get("application") == "fire":
        return True
    if answers.get("application") == "smoke":
        return answers.get("smoke_return") != "no_spring"
    return False


def _needs_control(answers: dict[str, str]) -> bool:
    return answers.get("need") == "actuator" and answers.get("application") not in (
        "fire",
        "smoke",
    )


def _needs_aux(answers: dict[str, str]) -> bool:
    if answers.get("need") == "kit":
        return True
    return _needs_control(answers)


def _after_voltage_or_control(answers: dict[str, str]) -> str:
    if _needs_temp_sensor(answers):
        return "temp_sensor"
    if _needs_aux(answers):
        return "aux_switch"
    return "damper_area"


def next_step(answers: dict[str, str], current: str) -> str | None:
    """Next question id or None (results) — port of ``nextStepAfter``."""
    match current:
        case "need":
            return {
                "actuator": "application",
                "ball_valve": "dn",
                "kit": "voltage",
                "adapter": "adapter_type",
            }.get(answers.get("need", ""))
        case "application":
            if answers.get("application") == "failsafe":
                return "failsafe_type"
            if answers.get("application") == "smoke":
                return "smoke_return"
            return "voltage"
        case "failsafe_type" | "smoke_return":
            return "voltage"
        case "voltage":
            if answers.get("need") == "kit":
                return "control"
            if answers.get("need") == "actuator":
                return "control" if _needs_control(answers) else _after_voltage_or_control(answers)
            return None
        case "control":
            if answers.get("need") == "kit":
                return "aux_switch" if _needs_aux(answers) else "dn"
            return _after_voltage_or_control(answers)
        case "temp_sensor":
            return "damper_area"
        case "aux_switch":
            return "dn" if answers.get("need") == "kit" else "damper_area"
        case "damper_area":
            return "damper_type"
        case "damper_type":
            return "damper_pressure"
        case "dn":
            return None if _is_flanged_dn(answers.get("dn")) else "kvs"
        case "kvs":
            return "ways"
        case _:
            return None


def apply_choice(answers: dict[str, str], step: str, choice: str) -> dict[str, str]:
    """Store answer + apply auto-locks from ``applyQuizChoice``."""
    next_answers = dict(answers)
    field = _STEP_FIELD.get(step)
    if field:
        next_answers[field] = choice
    if step == "need":
        next_answers = {"need": next_answers.get("need", "")}
    elif step == "application":
        next_answers = {
            "need": next_answers.get("need", ""),
            "application": next_answers.get("application", ""),
        }
    if step == "application" and next_answers.get("application") in ("fire", "smoke"):
        # Fire/smoke: only on/off in catalog — lock without asking.
        next_answers["control"] = "onoff"
    if step == "smoke_return" and next_answers.get("smoke_return") == "no_spring":
        next_answers["temp_sensor"] = "no"
    if step == "dn":
        if _is_flanged_dn(next_answers.get("dn")):
            next_answers["ways"] = "2"
            next_answers["kvs"] = "over_40"
        else:
            next_answers.pop("ways", None)
            next_answers.pop("kvs", None)
    return next_answers


# --- moment estimate (port of quizMomentEstimate.ts) ------------------------

_MOMENT_LADDER = (2, 4, 5, 6, 8, 10, 16, 20, 24, 32, 40)
_AREA_M2 = {
    "up_to_0_3": 0.3,
    "0_3_0_6": 0.6,
    "0_6_1_0": 1.0,
    "1_0_1_6": 1.6,
    "1_6_2_5": 2.5,
    "2_5_4_0": 4.0,
    "over_4": 5.0,
}
_PRESSURE_PA = {"low": 250, "medium": 450, "high": 800, "very_high": 1200}
_TYPE_K = {"round": 1.0, "rectangular": 1.4, "gate": 1.8}


def _ceil_ladder(required: float) -> int:
    for index, step in enumerate(_MOMENT_LADDER):
        if step >= required:
            if index + 1 < len(_MOMENT_LADDER) and required > step * 0.85:
                return _MOMENT_LADDER[index + 1]
            return step
    return _MOMENT_LADDER[-1]


def estimate_moment_nm(answers: dict[str, str]) -> int | None:
    """M = S × P × Kтип × Kзапас / 100 — port of ``estimateRequiredMomentNm``."""
    area = answers.get("damper_area", "")
    if not area or area == "skip":
        return None
    s = _AREA_M2[area]
    p = _PRESSURE_PA.get(answers.get("damper_pressure", ""), _PRESSURE_PA["medium"])
    k_type = _TYPE_K.get(answers.get("damper_type", ""), _TYPE_K["rectangular"])
    k_margin = 1.4 if answers.get("damper_pressure") == "very_high" else 1.3
    return _ceil_ladder(s * p * k_type * k_margin / 100)


# --- catalog params (port of quizFacetMatch.ts / quizToCatalog.ts) ----------

_VOLTAGE_24_RE = re.compile(r"\b24\b")
_VOLTAGE_230_RE = re.compile(r"230|240|100\s*[.…\-−–—]+\s*240")
_VOLTAGE_NOT_24_RE = re.compile(r"230|240|100")
_ONOFF_RE = re.compile(r"открыто\s*/\s*закрыто|вкл|on/off", re.IGNORECASE)
_FLOATING_RE = re.compile(r"2\s*[-–—]?\s*/\s*3|позицион", re.IGNORECASE)
_MODULATING_RE = re.compile(r"пропорциональн|модулир|плавн|0\s*[(.…\-−–—]?\s*10", re.IGNORECASE)
_MOMENT_NM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*н\s*·?\s*м", re.IGNORECASE)
_AREA_M2_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*м\s*²", re.IGNORECASE)

_AREA_CAP_LADDER: tuple[tuple[float, int], ...] = (
    (0.2, 2),
    (0.4, 4),
    (0.5, 5),
    (0.6, 6),
    (0.8, 8),
    (1.0, 10),
    (1.6, 16),
    (2.0, 20),
    (2.4, 24),
    (3.2, 32),
    (4.0, 40),
)

_KVS_BANDS = {
    "up_to_2_5": (None, 2.5),
    "2_5_to_6": (2.5, 6.3),
    "6_to_16": (6.3, 16),
    "16_to_40": (16, 40),
    "over_40": (40, None),
}


def _category_facets(category: str) -> dict[str, list[str]]:
    """Facet values for the resolved category (same source as /api/catalog/facets/)."""
    from catalog.facets import collect_facet_options
    from catalog.models import SKU

    qs = SKU.objects.filter(is_published=True, product__category__slug=category)
    facets = collect_facet_options(base_queryset=qs, category_slug=category)
    result: dict[str, list[str]] = {}
    for row in facets:
        values = row.get("values") if isinstance(row, dict) else None
        if isinstance(values, list):
            result[str(row["key"])] = [str(item["value"]) for item in values if isinstance(item, dict)]
    return result


def _match_voltage(values: list[str], choice: str) -> str | None:
    for value in values:
        raw = value.strip()
        if not raw:
            continue
        if choice == "24" and _VOLTAGE_24_RE.search(raw) and not _VOLTAGE_NOT_24_RE.search(raw):
            return value
        if choice == "230" and _VOLTAGE_230_RE.search(raw):
            return value
    return None


def _match_control(values: list[str], choice: str) -> str | None:
    on_off = floating = modulating = None
    for value in values:
        raw = value.strip()
        if not raw:
            continue
        if on_off is None and _ONOFF_RE.search(raw):
            on_off = value
        if floating is None and _FLOATING_RE.search(raw):
            floating = value
        if modulating is None and _MODULATING_RE.search(raw):
            modulating = value
    if choice == "modulating":
        return modulating
    discrete = [v for v in (floating, on_off) if v]
    return ",".join(dict.fromkeys(discrete)) or None


def _parse_nm(value: str) -> float | None:
    match = _MOMENT_NM_RE.search(value)
    return float(match.group(1).replace(",", ".")) if match else None


def _match_moment(values: list[str], target_nm: float) -> str | None:
    parsed = sorted(
        ((v, nm) for v in values if (nm := _parse_nm(v)) is not None),
        key=lambda row: row[1],
    )
    if not parsed:
        return None
    for value, nm in parsed:
        if nm == target_nm:
            return value
    for value, nm in parsed:
        if nm >= target_nm:
            return value
    return parsed[-1][0]


def _match_area_for_moment(values: list[str], target_nm: float) -> str | None:
    parsed = sorted(
        ((v, m2) for v in values if (m2 := _area_cap(v)) is not None),
        key=lambda row: row[1],
    )
    for value, m2 in parsed:
        if _moment_for_area_cap(m2) >= target_nm:
            return value
    return parsed[-1][0] if parsed else None


def _area_cap(value: str) -> float | None:
    match = _AREA_M2_RE.search(value)
    return float(match.group(1).replace(",", ".")) if match else None


def _moment_for_area_cap(cap_m2: float) -> int:
    for area, nm in _AREA_CAP_LADDER:
        if cap_m2 <= area + 0.001:
            return nm
    return 40


def _match_aux_switch(values: list[str], choice: str) -> str | None:
    if choice == "no":
        for value in values:
            if value.strip().lower() == "нет":
                return value
        return None
    for needle in ("SPDT-2", "SPDT-1"):
        for value in values:
            if needle.lower() in value.lower():
                return value
    return None


def _match_temp_sensor(values: list[str], choice: str) -> str | None:
    for value in values:
        raw = value.strip()
        if choice == "yes" and "saf72" in raw.lower():
            return value
        if choice == "no" and raw.lower() == "нет":
            return value
    return None


def _match_dn(values: list[str], dn: str) -> str | None:
    needle = re.compile(rf"\bDN\s*0*{re.escape(dn)}\b", re.IGNORECASE)
    for value in values:
        raw = value.strip()
        if needle.search(raw) or raw in (dn, f"DN{dn}"):
            return value
    return None


def _match_ways(values: list[str], ways: str) -> str | None:
    needle = re.compile(rf"{ways}\s*[-–—]?\s*ход", re.IGNORECASE)
    for value in values:
        if needle.search(value.strip()):
            return value
    return None


def _match_kvs(values: list[str], choice: str) -> str | None:
    low, high = _KVS_BANDS[choice]
    in_band = []
    for value in values:
        token = value.strip().split()[0].replace(",", ".") if value.strip() else ""
        try:
            kvs = float(token)
        except ValueError:
            continue
        if (low is None or kvs > low + 0.001) and (high is None or kvs <= high + 0.001):
            in_band.append((kvs, value))
    in_band.sort()
    return ",".join(dict.fromkeys(v for _, v in in_band)) or None


def _resolve_category(answers: dict[str, str]) -> str:
    need = answers.get("need", "")
    if need in ("ball_valve", "kit", "adapter"):
        return _CATEGORY[need]
    app = answers.get("application", "")
    if app in ("fire", "smoke", "fast"):
        return _CATEGORY[app]
    if app == "failsafe":
        key = "electronic" if answers.get("failsafe_type") == "electronic" else "spring"
        return _CATEGORY[key]
    return _CATEGORY["general"]


def quiz_catalog_url(answers: dict[str, str]) -> str:
    """Catalog path + facet query — same URL the on-site quiz navigates to."""
    category = _resolve_category(answers)
    facets = _category_facets(category)
    params: dict[str, str] = {}

    voltage = answers.get("voltage", "")
    if voltage and voltage != "skip":
        value = _match_voltage(facets.get("voltage", []), voltage)
        if value:
            params["voltage"] = value

    need = answers.get("need")
    skip_control = need == "actuator" and answers.get("application") in ("fire", "smoke")
    control = answers.get("control", "")
    if need in ("actuator", "kit") and not skip_control and control and control != "skip":
        value = _match_control(facets.get("control", []), control)
        if value:
            params["control"] = value

    if need == "actuator":
        estimated = estimate_moment_nm(answers)
        if estimated is not None:
            value = _match_moment(facets.get("moment", []), estimated)
            if value:
                params["moment"] = value
            value = _match_area_for_moment(facets.get("area", []), estimated)
            if value:
                params["area"] = value
        temp = answers.get("temp_sensor", "")
        if temp and temp != "skip":
            value = _match_temp_sensor(facets.get("temp_sensor", []), temp)
            if value:
                params["temp_sensor"] = value

    if need in ("actuator", "kit"):
        aux = answers.get("aux_switch", "")
        if aux and aux != "skip":
            value = _match_aux_switch(facets.get("aux_switch", []), aux)
            if value:
                params["aux_switch"] = value

    if need in ("ball_valve", "kit"):
        dn = answers.get("dn", "")
        if dn and dn != "skip":
            value = _match_dn(facets.get("dn", []), dn)
            if value:
                params["dn"] = value
        kvs = answers.get("kvs", "")
        if kvs and kvs != "skip":
            value = _match_kvs(facets.get("kvs", []), kvs)
            if value:
                params["kvs"] = value
        ways = answers.get("ways", "")
        if ways and ways != "skip":
            value = _match_ways(facets.get("ways", []), ways)
            if value:
                params["ways"] = value

    if need == "adapter" and answers.get("adapter_type") in ("br_m", "br_ml"):
        params["q"] = "BR-M" if answers["adapter_type"] == "br_m" else "BR-ML"

    if need == "actuator" and answers.get("application") == "smoke":
        smoke = answers.get("smoke_return", "")
        if smoke == "spring":
            params["q"] = "HVD"
        elif smoke == "no_spring":
            params["q"] = "SA"

    qs = urlencode(params)
    return f"/catalog/{category}?{qs}" if qs else f"/catalog/{category}"


# --- transcript state --------------------------------------------------------


def latest_quiz_message(conversation: Conversation) -> Message | None:
    """Last bot question awaiting an answer (parked if newer system msg exists)."""
    from supportchat.models import Message, MessageDirection

    quiz_msg = (
        Message.objects.filter(
            conversation=conversation,
            direction=MessageDirection.SYSTEM,
            raw_payload__quiz_step__isnull=False,
        )
        .order_by("-id")
        .first()
    )
    if quiz_msg is None:
        return None
    # Quiz is «parked» once any other system/bot message followed it.
    later = Message.objects.filter(
        conversation=conversation,
        direction__in=(MessageDirection.SYSTEM, MessageDirection.OUTBOUND),
        id__gt=quiz_msg.pk,
    ).exists()
    return None if later else quiz_msg


def _offer_pending(conversation: Conversation) -> bool:
    """Последнее сообщение бота — оффер квиза (для каналов без кнопок)."""
    from supportchat.models import Message, MessageDirection

    last = (
        Message.objects.filter(
            conversation=conversation,
            direction=MessageDirection.SYSTEM,
        )
        .order_by("-id")
        .first()
    )
    if last is None or not isinstance(last.raw_payload, dict):
        return False
    return bool(last.raw_payload.get("quiz_offer"))


def quiz_offer_actions() -> list[dict[str, str]]:
    return [
        {"id": QUIZ_START_ACTION, "label": "Подобрать в чате"},
        {"id": "call_manager", "label": "Позвать менеджера"},
    ]


def quiz_offer_text() -> str:
    return _QUIZ_OFFER_TEXT


# --- free-text answers --------------------------------------------------------

_YES_RE = re.compile(r"^(да|да\b|нужн|конечно|ага)\b", re.IGNORECASE)
_NO_RE = re.compile(r"^(нет|не\b|не нужн|без)\b", re.IGNORECASE)
_DONT_KNOW_RE = re.compile(r"не\s+знаю|не\s+уверен|пока\s+не\s+понятн|любой|всё\s+равно", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _parse_yes_no(text: str) -> str | None:
    if _DONT_KNOW_RE.search(text):
        return "skip"
    if _YES_RE.search(text):
        return "yes"
    if _NO_RE.search(text):
        return "no"
    return None


def parse_step_answer(step: str, text: str) -> str | None:
    """Map free-text reply to a choice id for the pending quiz step."""
    body = (text or "").strip()
    if not body:
        return None
    low = body.casefold()
    if _DONT_KNOW_RE.search(low):
        _, _, skippable = _STEPS[step]
        return "skip" if skippable else None

    if step == "need":
        from supportchat.gigachat.triage_product import _product_kind

        if re.search(r"кронштейн|адаптер|br[\s-]*m", low):
            return "adapter"
        kind = _product_kind(body)
        return {"kit": "kit", "ball": "ball_valve", "actuator": "actuator"}.get(kind)
    if step == "application":
        if re.search(r"противопожар|огнезадерж|\bозк\b", low):
            return "fire"
        if re.search(r"дым", low):
            return "smoke"
        if re.search(r"быстр|ускорен", low):
            return "fast"
        if re.search(r"отключени|fail[\s-]*safe|возврат", low):
            return "failsafe"
        if re.search(r"обычн|вентиляц|кондицион|приток|вытяж", low):
            return "general"
        return None
    if step == "failsafe_type":
        if re.search(r"электрон|конденсат|\bqx\b", low):
            return "electronic"
        if re.search(r"пружин|\bfu\b", low):
            return "spring"
        return None
    if step == "smoke_return":
        if re.search(r"без\s+пружин", low):
            return "no_spring"
        if re.search(r"пружин", low):
            return "spring"
        return None
    if step == "voltage":
        if re.search(r"\b(230|220)\b", low):
            return "230"
        if re.search(r"\b24\b", low):
            return "24"
        return None
    if step == "control":
        if re.search(r"плавн|пропорц|модулир|0\s*[-–—.]?\s*10", low):
            return "modulating"
        if re.search(r"открыт|закрыт|дискрет|позиц|реле", low):
            return "onoff"
        return None
    if step in ("aux_switch", "temp_sensor"):
        return _parse_yes_no(low)
    if step == "damper_area":
        match = _NUMBER_RE.search(low.replace(",", "."))
        if not match:
            return None
        area = float(match.group(1))
        for choice, cap in _AREA_M2.items():
            if area <= cap:
                return choice
        return "over_4"
    if step == "damper_type":
        if re.search(r"кругл", low):
            return "round"
        if re.search(r"шибер|ножев", low):
            return "gate"
        if re.search(r"прямоуг|квадрат", low):
            return "rectangular"
        return None
    if step == "damper_pressure":
        match = _NUMBER_RE.search(low)
        if not match:
            return None
        pressure = float(match.group(1).replace(",", "."))
        if pressure <= 300:
            return "low"
        if pressure <= 600:
            return "medium"
        if pressure <= 1000:
            return "high"
        return "very_high"
    if step == "dn":
        match = re.search(r"(?:dn|ду|диаметр)?\s*(\d{2,3})", low)
        if match and match.group(1) in {
            "15",
            "20",
            "25",
            "32",
            "40",
            "50",
            "65",
            "80",
            "100",
            "125",
            "150",
        }:
            return match.group(1)
        return None
    if step == "kvs":
        match = _NUMBER_RE.search(low.replace(",", "."))
        if not match:
            return None
        kvs = float(match.group(1))
        for choice, (low_b, high_b) in _KVS_BANDS.items():
            if (low_b is None or kvs > low_b) and (high_b is None or kvs <= high_b):
                return choice
        return None
    if step == "ways":
        if re.search(r"\b2\b|двухход|2\s*[-–—]?\s*ход", low):
            return "2"
        if re.search(r"\b3\b|тр[её]хход|3\s*[-–—]?\s*ход", low):
            return "3"
        return None
    if step == "adapter_type":
        if re.search(r"br[\s-]*ml|с\s+пружин", low):
            return "br_ml"
        if re.search(r"br[\s-]*m|без\s+пружин|\bmu\b|\bmqu\b", low):
            return "br_m"
        return None
    return None


# --- replies -----------------------------------------------------------------


def _question_body(step: str) -> str:
    question, _, _ = _STEPS[step]
    return question


def _step_actions(step: str) -> list[dict[str, str]]:
    _, choices, skippable = _STEPS[step]
    actions = [{"id": f"{QUIZ_ACTION_PREFIX}{step}:{choice}", "label": label} for choice, label in choices]
    if skippable:
        actions.append({"id": f"{QUIZ_ACTION_PREFIX}{step}:skip", "label": _SKIP_LABEL})
    return actions


def _summary_chips(answers: dict[str, str]) -> str:
    """Compact «Вы выбрали: …» line for the results message."""
    chips: list[str] = []
    need_labels = {
        "actuator": "Привод",
        "ball_valve": "Шаровой кран",
        "kit": "Комплект",
        "adapter": "Адаптер",
    }
    if answers.get("need") in need_labels:
        chips.append(need_labels[answers["need"]])
    app = answers.get("application") or ""
    chips.append(
        {
            "general": "Вентиляция",
            "fire": "ОЗК",
            "smoke": "Дымоудаление",
            "failsafe": "Возврат при отключении",
            "fast": "Быстрый ход",
        }.get(app, ""),
    )
    if answers.get("voltage") in ("24", "230"):
        chips.append(f"{answers['voltage']} В")
    if answers.get("control") == "onoff":
        chips.append("Открыть/закрыть")
    if answers.get("control") == "modulating":
        chips.append("0–10 В")
    if answers.get("dn") and answers["dn"] != "skip":
        chips.append(f"DN {answers['dn']}")
    if answers.get("ways") in ("2", "3"):
        chips.append(f"{answers['ways']}-ходовой")
    moment = estimate_moment_nm(answers)
    if moment is not None:
        chips.append(f"~{moment} Нм")
    return " · ".join(part for part in chips if part)


def _ask_step(answers: dict[str, str], step: str) -> Any:
    """AiReply for one quiz question; state persists in payload_extra."""
    from supportchat.gigachat.chat_actions import actions_payload
    from supportchat.gigachat.reply import AiReply

    return AiReply(
        text=_question_body(step),
        escalate=False,
        escalation_note="",
        payload_extra={
            **actions_payload(_step_actions(step)),
            "quiz_step": step,
            "quiz_answers": answers,
        },
    )


def _results_reply(answers: dict[str, str]) -> Any:
    from supportchat.gigachat.chat_actions import actions_payload, call_manager_only_actions
    from supportchat.gigachat.reply import AiReply

    url = quiz_catalog_url(answers)
    chips = _summary_chips(answers)
    lines = ["Подобрал подборку в каталоге:"]
    if chips:
        lines.append(f"Вы выбрали: {chips}.")
    lines.extend(
        [
            url,
            "Если нужно точнее — напишите «позовите менеджера», он сверит по проекту.",
        ],
    )
    return AiReply(
        text="\n".join(lines),
        escalate=False,
        escalation_note="",
        payload_extra={
            **actions_payload(call_manager_only_actions()),
            "quiz_done": True,
            "quiz_answers": answers,
        },
    )


def _advance(answers: dict[str, str], step: str, choice: str) -> Any:
    answers = apply_choice(answers, step, choice)
    nxt = next_step(answers, step)
    if nxt is None:
        return _results_reply(answers)
    return _ask_step(answers, nxt)


def _infer_need(conversation: Conversation, before_id: int | None) -> str | None:
    """Guess «need» from the user's earlier product message."""
    from supportchat.gigachat.triage_product import _product_kind
    from supportchat.models import Message, MessageDirection

    qs = Message.objects.filter(
        conversation=conversation,
        direction=MessageDirection.INBOUND,
    ).order_by("-id")
    if before_id is not None:
        qs = qs.filter(id__lt=before_id)
    for row in qs[:5]:
        text = row.body or ""
        if re.search(r"кронштейн|адаптер|br[\s-]*m", text, re.IGNORECASE):
            return "adapter"
        kind = _product_kind(text)
        if kind == "kit":
            return "kit"
        if kind == "ball":
            return "ball_valve"
        if re.search(r"привод|заслонк|клапан", text, re.IGNORECASE):
            return "actuator"
    return None


def _quiz_state(msg: Message | None) -> tuple[str, dict[str, str]]:
    """(step, answers) from a quiz SYSTEM message payload."""
    raw = msg.raw_payload if msg is not None and isinstance(msg.raw_payload, dict) else {}
    step = str(raw.get("quiz_step", ""))
    answers = raw.get("quiz_answers")
    return step, answers if isinstance(answers, dict) else {}


def triage_quiz_reply(
    conversation: Conversation,
    user_query: str,
    payload: dict[str, object] | None,
    *,
    inbound_message: Message | None = None,
) -> Any | None:
    """Handle quiz buttons / free-text answers; None → normal pipeline."""
    action = inbound_chat_action(payload)
    pending = latest_quiz_message(conversation)

    if not action and pending is None and _offer_pending(conversation):
        # Канал без кнопок: «давай» или свежий product-сигнал → старт.
        from supportchat.gigachat.triage_product import _product_kind

        fresh_need = None
        if re.search(
            r"кран|привод|комплект|заслонк|клапан|кронштейн|адаптер|br[\s-]*m",
            user_query,
            re.IGNORECASE,
        ):
            fresh_need = {"kit": "kit", "ball": "ball_valve", "actuator": "actuator"}.get(_product_kind(user_query))
            if re.search(r"кронштейн|адаптер|br[\s-]*m", user_query, re.IGNORECASE):
                fresh_need = "adapter"
        if fresh_need or _QUIZ_START_TEXT_RE.search(user_query):
            if fresh_need is None:
                fresh_need = _infer_need(conversation, inbound_message.pk if inbound_message else None)
            state = {"need": fresh_need} if fresh_need else {}
            step = next_step(state, "need") if fresh_need else "need"
            if step is None:
                return _results_reply(state)
            return _ask_step(state, step)

    if action == QUIZ_START_ACTION or action == QUIZ_RESTART_ACTION:
        need = _infer_need(conversation, inbound_message.pk if inbound_message else None)
        state = {"need": need} if need else {}
        step = next_step(state, "need") if need else "need"
        if step is None:
            return _results_reply(state)
        return _ask_step(state, step)

    if action.startswith(QUIZ_ACTION_PREFIX):
        parts = action.split(":", 2)
        pending_step, answers_now = _quiz_state(pending)
        if len(parts) != 3 or pending is None:
            # Клик по устаревшей кнопке — переспросим актуальный шаг.
            if pending_step in _STEPS:
                return _ask_step(answers_now, pending_step)
            return None
        _, step, choice = parts
        if step != pending_step or step not in _STEPS:
            return _ask_step(answers_now, pending_step)
        return _advance(answers_now, step, choice)

    if pending is not None:
        step, answers_now = _quiz_state(pending)
        if step not in _STEPS:
            return None
        raw = pending.raw_payload if isinstance(pending.raw_payload, dict) else {}
        parsed = parse_step_answer(step, user_query)
        if parsed is None:
            if raw.get("quiz_reasked"):
                # Второй раз не поняли — отпускаем вопрос в обычный пайплайн.
                return None
            from supportchat.gigachat.chat_actions import actions_payload
            from supportchat.gigachat.reply import AiReply

            return AiReply(
                text=f"{_QUIZ_REASK_TEXT}\n\n{_question_body(step)}",
                escalate=False,
                escalation_note="",
                payload_extra={
                    **actions_payload(_step_actions(step)),
                    "quiz_step": step,
                    "quiz_answers": answers_now,
                    "quiz_reasked": True,
                },
            )
        return _advance(answers_now, step, parsed)

    return None
