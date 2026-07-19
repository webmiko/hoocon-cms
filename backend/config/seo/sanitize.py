"""Path validation and plain-text meta helpers (БЗ M1/M3/M7)."""

from __future__ import annotations

import re
from html import unescape

from django.http import Http404
from django.utils.html import strip_tags

from config.seo.routes import SLUG_RE

_META_MAX_LEN = 300
_PATH_ALLOWED_RE = re.compile(r"^/[a-zA-Z0-9/_-]*$")


def normalize_spa_path(raw_path: str) -> str:
    """Normalize SPA pathname; raise Http404 on dangerous input.

    Args:
        raw_path: Request path (may include query/hash).

    Returns:
        Canonical path without trailing slash (except ``/``).

    Raises:
        Http404: Path traversal, encoding tricks, or illegal characters.
    """
    path = raw_path.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    if "%" in path or "\\" in path or ".." in path.split("/"):
        raise Http404
    path = path.rstrip("/") or "/"
    if path != "/" and not _PATH_ALLOWED_RE.fullmatch(path):
        raise Http404
    return path


def validate_slug(slug: str) -> str:
    """Validate a URL slug against the allowlist regex.

    Args:
        slug: Path segment.

    Returns:
        The same slug if valid.

    Raises:
        Http404: Invalid or empty slug.
    """
    if not slug or len(slug) > 300 or not re.fullmatch(SLUG_RE, slug):
        raise Http404
    return slug


def plain_text_for_meta(value: str, *, max_len: int = _META_MAX_LEN) -> str:
    """Strip HTML and truncate for meta description / titles.

    Args:
        value: Raw HTML or plain text.
        max_len: Max characters (default 300).

    Returns:
        Plain text suitable for meta tags.
    """
    text = strip_tags(unescape(value.replace("\x00", "")))
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    truncated = text[: max_len - 1].rsplit(" ", 1)[0]
    return f"{truncated}…" if truncated else text[:max_len]
