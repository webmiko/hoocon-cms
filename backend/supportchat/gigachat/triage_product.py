"""Product selection in triage: clarify, catalog/quiz links, no model picks."""

from __future__ import annotations

import re

from supportchat.gigachat.manuals_kb import extract_voltage_hint
from supportchat.gigachat.triage import is_product_intent
from supportchat.models import Conversation, Message, MessageDirection

_CATALOG_DAMPERS = "/catalog/elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"
_CATALOG_FIRE = "/catalog/elektroprivody-protivopozharnye-i-dymovye"
_CATALOG_FAST = "/catalog/elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata"
_CATALOG_BALL = "/catalog/sharovye-krany"
_QUIZ_PATH = "/#podbor"
_RFQ_PATH = "/rfq"

_SERIES_CODE_RE = re.compile(r"(?i)\b(?:da|sa|hva|hvd)\b")
_SERIES_NAV: tuple[tuple[str, str, str], ...] = (
    ("da", "DA", "общеобменная вентиляция, без пружинного возврата"),
    ("sa", "SA", "противопожарные и дымовые клапаны"),
    ("hva", "HVA", "ускоренные приводы"),
    ("hvd", "HVD", "воздушные заслонки без пружинного возврата"),
)

_FORBIDDEN_OUTPUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"##\s*\[", re.IGNORECASE),
    re.compile(r"\bDA[A-Z0-9]{2,}", re.IGNORECASE),
    re.compile(r"\bSA[A-Z0-9]{2,}", re.IGNORECASE),
    re.compile(r"\bHV[A-Z0-9]{2,}", re.IGNORECASE),
    re.compile(r"рекомендуем\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*н·м\b", re.IGNORECASE),
    re.compile(r"\bmanual\.", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:руб|₽|rub)\b", re.IGNORECASE),
    re.compile(r"\b(?:срок\w*\s+поставк|в\s+наличии\s+на\s+складе)\b", re.IGNORECASE),
    re.compile(r"\b(?:обычно|как\s+правило|по\s+опыту)\b", re.IGNORECASE),
)

_AREA_RE = re.compile(
    r"(?i)(\d+(?:[.,]\d+)?)\s*(?:кв\.?\s*м|м2|м²|квадрат)",
)
_FIRE_RE = re.compile(r"(?i)\b(?:противопожар|дымо|пожар)")
_BALL_RE = re.compile(r"(?i)\b(?:шаровой\s+кран|кран\b)")


def triage_response_violates_policy(text: str) -> bool:
    """Triage bot must not recommend models or cite KB branches."""
    body = (text or "").strip()
    if not body:
        return False
    return any(pattern.search(body) for pattern in _FORBIDDEN_OUTPUT_PATTERNS)


def product_clarification_already_sent(conversation: Conversation) -> bool:
    """Whether we already asked qualifying questions for a product request."""
    return Message.objects.filter(
        conversation=conversation,
        direction=MessageDirection.SYSTEM,
        raw_payload__ai_product_clarify=True,
    ).exists()


def thread_has_product_topic(history: list[dict[str, str]]) -> bool:
    """Any user line in the thread is about products/selection."""
    for row in history:
        if row.get("role") == "user" and is_product_intent(str(row.get("content", ""))):
            return True
    return False


def build_product_handoff_note(history: list[dict[str, str]]) -> str:
    """Compact facts from the thread for managers."""
    parts: list[str] = []
    for row in history:
        if row.get("role") != "user":
            continue
        line = str(row.get("content", "")).strip().replace("\n", " ")
        if line:
            parts.append(line[:200])
    joined = " | ".join(parts)
    return joined[:500]


def _catalog_hint(text: str) -> str:
    if _FIRE_RE.search(text):
        return _CATALOG_FIRE
    if _BALL_RE.search(text):
        return _CATALOG_BALL
    return _CATALOG_DAMPERS


def mentioned_series_codes(text: str) -> tuple[str, ...]:
    """Series codes DA/SA/HVA/HVD mentioned in the user message."""
    found = {match.group(0).casefold() for match in _SERIES_CODE_RE.finditer(text or "")}
    order = ("da", "sa", "hva", "hvd")
    return tuple(code for code in order if code in found)


def _series_catalog_path(code: str) -> str:
    if code == "sa":
        return _CATALOG_FIRE
    if code == "hva":
        return _CATALOG_FAST
    return _CATALOG_DAMPERS


def triage_multi_series_catalog_reply(text: str) -> str:
    """B2B-style request for several series — category links, no SKU picks."""
    body = (text or "").strip()
    series = mentioned_series_codes(body)
    volt = extract_voltage_hint(body)
    lines = ["Понял запрос по приводам Hoocon."]
    if volt == "24":
        lines.append("Напряжение: 24 В (в каталоге — фильтр AC/DC 24 В).")
    elif volt == "230":
        lines.append("Напряжение: 230 В (в каталоге — фильтр AC 100…240 В).")
    else:
        lines.append("Напряжение: уточните 24 В или 230 В — в артикулах это разные исполнения.")
    lines.append("Категории по сериям:")
    for code, title, description in _SERIES_NAV:
        if code not in series:
            continue
        lines.append(f"— {title}: {description} → {_series_catalog_path(code)}")
    lines.extend(
        [
            (
                "Для коммерческого предложения укажите количество и момент (Н·м) по каждой серии "
                f"или оформите запрос на {_RFQ_PATH}. Когда будете готовы к подбору — "
                "напишите «позовите менеджера»."
            ),
            f"Квиз на главной: {_QUIZ_PATH}.",
        ],
    )
    return "\n".join(lines)


def triage_product_clarification_reply(text: str) -> str:
    """First response to a product/sizing question — questions only, no models."""
    body = (text or "").strip()
    if mentioned_series_codes(body):
        return triage_multi_series_catalog_reply(body)
    catalog = _catalog_hint(body)
    area_match = _AREA_RE.search(body)
    lines = [
        "Чтобы менеджер подобрал привод точно, уточните, пожалуйста:",
    ]
    if area_match:
        lines.append(
            f"— для заслонки ~{area_match.group(1)} м²: перепад давления (Па) или расход воздуха;",
        )
    else:
        lines.append("— тип арматуры (заслонка, клапан, шаровой кран) и размер/площадь;")
    lines.extend(
        [
            "— напряжение: 24 В или 230 В;",
            "— нужен ли пружинный возврат (fail-safe), если применимо.",
            (
                f"Пока я не умею подбирать модели сам — можете заглянуть в категорию {catalog} "
                f"или в квиз на главной {_QUIZ_PATH}."
            ),
        ],
    )
    return "\n".join(lines)


def triage_product_followup_reply(_history: list[dict[str, str]]) -> str:
    """After clarification — bot keeps helping; manager only on explicit request."""
    return (
        "Спасибо за уточнения! Зафиксировал детали. Пока могу подсказать раздел каталога "
        f"или квиз {_QUIZ_PATH}. Когда нужен подбор модели — напишите «позовите менеджера»."
    )
