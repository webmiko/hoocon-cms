"""Strip active content from staff Wiki HTML before save."""

from __future__ import annotations

import re

_SCRIPT_STYLE_RE = re.compile(
    r"<\s*(?:script|iframe|object|embed|form)\b[^>]*>.*?</\s*(?:script|iframe|object|embed|form)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_SELF_CLOSING_ACTIVE_RE = re.compile(
    r"<\s*(?:script|iframe|object|embed|form)\b[^>]*/\s*>",
    re.IGNORECASE,
)
_EVENT_HANDLER_ATTR_RE = re.compile(
    r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""",
    re.IGNORECASE,
)
_JAVASCRIPT_URL_RE = re.compile(
    r"""(href|src|xlink:href)\s*=\s*(["'])\s*javascript:[^"']*\2""",
    re.IGNORECASE,
)


def sanitize_wiki_html(body: str) -> str:
    """Remove script-like tags and inline handlers; keep manager markup."""
    text = body or ""
    if not text.strip():
        return text
    text = _SCRIPT_STYLE_RE.sub("", text)
    text = _SELF_CLOSING_ACTIVE_RE.sub("", text)
    text = _EVENT_HANDLER_ATTR_RE.sub("", text)
    text = _JAVASCRIPT_URL_RE.sub(r'\1="#"', text)
    return text
