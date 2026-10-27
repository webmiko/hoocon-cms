"""Turn site paths into absolute URLs for messenger delivery."""

from __future__ import annotations

import re
from urllib.parse import urlparse

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


def _trusted_site_base(raw_base: str) -> str:
    """Only expand links when base host matches SITE_URL (blocks hoocon.ru.evil.com)."""
    default = "https://hoocon.ru"
    site_url = (getattr(settings, "SITE_URL", None) or default).strip()
    parsed_site = urlparse(site_url if "://" in site_url else f"https://{site_url}")
    allowed_host = (parsed_site.hostname or "hoocon.ru").lower().rstrip(".")
    candidate = (raw_base or site_url or default).strip()
    if "://" not in candidate:
        candidate = f"https://{candidate.lstrip('/')}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return parsed_site.geturl().rstrip("/") or default.rstrip("/")
    if host == allowed_host or host.endswith(f".{allowed_host}"):
        return f"{parsed.scheme or 'https'}://{host}".rstrip("/")
    return parsed_site.geturl().rstrip("/") or default.rstrip("/")


def expand_site_links_for_messenger(text: str, *, base_url: str | None = None) -> str:
    """Absolute hoocon.ru links for Telegram/MAX; web widget keeps relative paths."""
    body = text or ""
    if not body:
        return body
    raw_base = base_url or getattr(settings, "SITE_URL", None) or "https://hoocon.ru"
    base = _trusted_site_base(str(raw_base))

    def _replace(match: re.Match[str]) -> str:
        return f"{base}{match.group(1)}"

    return _SITE_LINK_RE.sub(_replace, body)
