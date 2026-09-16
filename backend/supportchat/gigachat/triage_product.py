"""Product selection in triage: clarify, catalog/quiz links, no model picks."""

from __future__ import annotations

import re

from supportchat.gigachat.triage import is_product_intent
from supportchat.models import Conversation, Message, MessageDirection

_CATALOG_DAMPERS = "/catalog/elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"
_CATALOG_FIRE = "/catalog/elektroprivody-protivopozharnye-i-dymovye"
_CATALOG_BALL = "/catalog/sharovye-krany"
_QUIZ_PATH = "/#podbor"

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


def triage_product_clarification_reply(text: str) -> str:
    """First response to a product/sizing question — questions only, no models."""
    body = (text or "").strip()
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


def triage_product_followup_handoff(history: list[dict[str, str]]) -> tuple[str, str]:
    """After clarification — hand off to a human with thread summary."""
    note = build_product_handoff_note(history)
    text = (
        "Спасибо за уточнения! Переключаю чат на менеджера — он подберёт подходящий "
        "вариант и ответит здесь. Если удобнее самостоятельно: каталог по категориям "
        f"или квиз {_QUIZ_PATH} на главной."
    )
    return text, note or "Запрос на подбор продукции."
