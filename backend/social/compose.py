"""Compose plain-text social announcements for Article / News."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from content.models import Article, News

_MAX_EXCERPT_LEN = 280


def _public_url(path: str) -> str:
    """Join SITE_URL with a path starting with /."""
    base = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def content_path(obj: models.Model) -> str:
    """Return public path for Article or News.

    Args:
        obj: published content instance.

    Returns:
        Path like ``/statyi/<slug>`` or ``/novosti/<slug>``.

    Raises:
        TypeError: if ``obj`` is not Article or News.
    """
    if isinstance(obj, Article):
        return f"/statyi/{obj.slug}"
    if isinstance(obj, News):
        return f"/novosti/{obj.slug}"
    raise TypeError(f"Unsupported content type: {type(obj)!r}")


def compose_announcement(obj: models.Model) -> str:
    """Build announcement text for Telegram / VK / MAX.

    Args:
        obj: Article or News instance.

    Returns:
        Multiline UTF-8 text with title, short body, and absolute URL.
    """
    title = (getattr(obj, "title", "") or "").strip()
    excerpt = ""
    if isinstance(obj, Article):
        excerpt = (obj.excerpt or "").strip()
    if not excerpt:
        body = (getattr(obj, "body", "") or "").strip()
        # Strip coarse HTML tags for social preview.
        plain = body.replace("<br>", "\n").replace("<br/>", "\n").replace("<p>", "").replace("</p>", "\n")
        while "<" in plain and ">" in plain:
            start = plain.find("<")
            end = plain.find(">", start)
            if end == -1:
                break
            plain = plain[:start] + plain[end + 1 :]
        excerpt = " ".join(plain.split())
    if len(excerpt) > _MAX_EXCERPT_LEN:
        excerpt = excerpt[: _MAX_EXCERPT_LEN - 1].rstrip() + "…"

    url = _public_url(content_path(obj))
    kind = "Статья" if isinstance(obj, Article) else "Новость"
    lines = [f"{kind}: {title}", ""]
    if excerpt:
        lines.extend([excerpt, ""])
    lines.append(url)
    return "\n".join(lines).strip()
