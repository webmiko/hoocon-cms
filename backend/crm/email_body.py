"""Helpers for CRM outbound email bodies (plain text vs HTML)."""

from __future__ import annotations

import re

from django.utils.html import strip_tags

_HTML_TAG_RE = re.compile(
    r"<(p|br|div|ul|ol|li|b|strong|i|em|a|span|h[1-6])\b",
    re.IGNORECASE,
)


def is_html_email_body(body: str) -> bool:
    """True when the stored body should be sent as HTML."""
    text = (body or "").strip()
    if not text.startswith("<"):
        return False
    return bool(_HTML_TAG_RE.search(text))


def html_email_to_plain(body: str) -> str:
    """Best-effort plain text for multipart/alternative."""
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = strip_tags(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
