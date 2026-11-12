"""Helpers for CRM email bodies (plain text vs HTML)."""

from __future__ import annotations

import html
import re

from django.utils.html import strip_tags

_HTML_TAG_RE = re.compile(
    r"<(p|br|div|ul|ol|li|b|strong|i|em|a|span|h[1-6])\b",
    re.IGNORECASE,
)
# Any HTML tag, not only the compose allowlist: img/iframe must not stay in the card.
_HTML_MARKUP_RE = re.compile(
    r"</?[a-zA-Z][\w:-]*\b|<!DOCTYPE|<!--",
    re.IGNORECASE,
)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_ANCHOR_RE = re.compile(
    r"""<a\b[^>]*\bhref=["']([^"']*)["'][^>]*>(.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_END_RE = re.compile(
    r"</(?:p|div|li|tr|h[1-6]|blockquote)>",
    re.IGNORECASE,
)


def is_html_email_body(body: str) -> bool:
    """True when the stored body should be sent as HTML."""
    text = (body or "").strip()
    if not text.startswith("<"):
        return False
    return bool(_HTML_TAG_RE.search(text))


def email_body_has_markup(body: str) -> bool:
    """True when the text still contains HTML tags, not just a comparison sign."""
    return bool(_HTML_MARKUP_RE.search(body or ""))


def _anchor_to_text(match: re.Match[str]) -> str:
    """Keep a link readable: the label, and the address when it differs."""
    href = html.unescape(match.group(1) or "").replace("\xa0", " ").strip()
    label = strip_tags(match.group(2) or "")
    label = html.unescape(label).replace("\xa0", " ").strip()
    if not href or href.lower().startswith(("javascript:", "data:")):
        return label
    if not label or label == href:
        return href
    return f"{label} ({href})"


def html_email_to_plain(body: str) -> str:
    """Readable letter text: no tags, links kept, HTML entities decoded."""
    text = _SCRIPT_STYLE_RE.sub("", body or "")
    text = _ANCHOR_RE.sub(_anchor_to_text, text)
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_END_RE.sub("\n\n", text)
    text = strip_tags(text)
    text = html.unescape(text).replace("\xa0", " ")
    # Unescape can turn &lt;script&gt; back into a tag. Strip once more.
    text = strip_tags(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def email_body_for_reading(body: str) -> str:
    """Body as a manager should see it in the letter card."""
    text = body or ""
    if not email_body_has_markup(text):
        return text
    return html_email_to_plain(text)
