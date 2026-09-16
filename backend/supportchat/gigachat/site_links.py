"""Turn site paths into absolute URLs for messenger delivery."""

from __future__ import annotations

import re

from django.conf import settings

# Same public routes the bot may mention; keep in sync with triage nav / widget.
_SITE_LINK_RE = re.compile(
    r"(?<![\w.])"
    r"(/(?:"
    r"(?:dokumentaciya|catalog|gde-kupit|kontakty|consultation|faq|zavod|company|rfq|search)"
    r"(?:/[a-z0-9][a-z0-9-]*)*"
    r")(?:\?[^\s.,;:!?)»\"']+)?(?:\#[a-z0-9-]+)?|/\#[a-z0-9-]+)",
    re.IGNORECASE,
)


def expand_site_links_for_messenger(text: str, *, base_url: str | None = None) -> str:
    """Absolute hoocon.ru links for Telegram/MAX; web widget keeps relative paths."""
    body = text or ""
    if not body:
        return body
    raw_base = base_url or getattr(settings, "SITE_URL", None) or "https://hoocon.ru"
    base = str(raw_base).rstrip("/")

    def _replace(match: re.Match[str]) -> str:
        return f"{base}{match.group(1)}"

    return _SITE_LINK_RE.sub(_replace, body)
