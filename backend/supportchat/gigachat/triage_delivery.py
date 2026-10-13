"""Delivery questions: shipments are only within Russia for now."""

from __future__ import annotations

import re

_DELIVERY_RE = re.compile(
    r"(?i)\b(?:доставк\w*|доставить|доставля\w*|отгрузк\w*|отгрузить)\b",
)
_DELIVERY_REPLY = (
    "Доставку пока осуществляем только по России. "
    "Если вам нужна отправка за её пределы, напишите, пожалуйста, — "
    "передадим вопрос менеджеру."
)


def triage_delivery_reply(text: str) -> str | None:
    """Respectful answer when the visitor asks about shipping."""
    if not _DELIVERY_RE.search(text or ""):
        return None
    return _DELIVERY_REPLY
