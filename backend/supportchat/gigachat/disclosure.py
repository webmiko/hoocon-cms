"""Bot disclosure for the first assistant reply in triage/full modes."""

from __future__ import annotations

BOT_SENDER_NAME = "Бот Hoocon"

_BOT_DISCLOSURE_PREFIX = "Здравствуйте! С вами на связи автоматический помощник Hoocon. "


def apply_bot_disclosure(text: str, *, first_turn: bool) -> str:
    """Prefix the first bot reply so the visitor knows it is not a human."""
    body = (text or "").strip()
    if not body or not first_turn:
        return body
    lowered = body.casefold()
    if "бот" in lowered or "автоматическ" in lowered or "не менеджер" in lowered:
        return body
    return f"{_BOT_DISCLOSURE_PREFIX}{body}"
