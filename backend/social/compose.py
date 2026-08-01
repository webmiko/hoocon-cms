"""Compose social announcements for Article / News (plain text + Telegram HTML)."""

from __future__ import annotations

import html
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils.html import strip_tags

from content.models import Article, News

_MAX_EXCERPT_LEN = 280
# Telegram Bot API caption limit for sendPhoto / sendVideo / …
_TELEGRAM_CAPTION_MAX = 1024


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


def _plain_excerpt(obj: models.Model) -> str:
    """Plain-text excerpt: strip tags, unescape entities, collapse whitespace."""
    raw = ""
    if isinstance(obj, Article):
        raw = (obj.excerpt or "").strip()
    if not raw:
        raw = (getattr(obj, "body", "") or "").strip()
    text = html.unescape(strip_tags(raw))
    # strip_tags leaves entity-only leftovers; collapse whitespace.
    text = " ".join(text.split())
    if len(text) > _MAX_EXCERPT_LEN:
        text = text[: _MAX_EXCERPT_LEN - 1].rstrip() + "…"
    return text


def compose_announcement(obj: models.Model) -> str:
    """Build plain-text announcement for VK / MAX (and previews).

    Args:
        obj: Article or News instance.

    Returns:
        Multiline UTF-8 text with title, short body, and absolute URL.
    """
    title = (getattr(obj, "title", "") or "").strip()
    excerpt = _plain_excerpt(obj)
    url = _public_url(content_path(obj))
    kind = "Статья" if isinstance(obj, Article) else "Новость"
    lines = [f"{kind}: {title}", ""]
    if excerpt:
        lines.extend([excerpt, ""])
    lines.append(url)
    return "\n".join(lines).strip()


def compose_telegram_announcement(obj: models.Model) -> str:
    """Build Telegram HTML announcement (``parse_mode=HTML``).

    Allowed tags are Telegram's HTML subset only (``<b>``, ``<i>``, ``<a>``, …).
    User content is HTML-escaped so CMS tags never leak into the channel.
    Length fits ``sendPhoto`` caption (≤1024).

    Args:
        obj: Article or News instance.

    Returns:
        Multiline HTML string for ``sendMessage`` / ``sendPhoto`` caption.
    """
    title = html.escape((getattr(obj, "title", "") or "").strip())
    excerpt = html.escape(_plain_excerpt(obj))
    url = html.escape(_public_url(content_path(obj)))
    if isinstance(obj, Article):
        kind_emoji = "📄"
        kind = "Статья"
    else:
        kind_emoji = "📰"
        kind = "Новость"

    footer = f'<a href="{url}">Читать на сайте →</a>'
    header = f"{kind_emoji} <b>{kind}: {title}</b>"
    # Reserve room for blank lines + footer inside caption limit.
    budget = _TELEGRAM_CAPTION_MAX - len(header) - len(footer) - 4
    if budget < 0:
        budget = 0
    if excerpt and len(excerpt) > budget:
        excerpt = excerpt[: max(0, budget - 1)].rstrip() + "…"

    lines = [header, ""]
    if excerpt and budget > 0:
        lines.extend([excerpt, ""])
    lines.append(footer)
    text = "\n".join(lines).strip()
    if len(text) > _TELEGRAM_CAPTION_MAX:
        text = text[: _TELEGRAM_CAPTION_MAX - 1].rstrip() + "…"
    return text


def content_cover_path(obj: models.Model) -> Path | None:
    """Local filesystem path to Article/News cover when the file exists."""
    cover = getattr(obj, "cover", None)
    if cover is None or not getattr(cover, "name", None):
        return None
    try:
        path = Path(cover.path)
    except (ValueError, NotImplementedError, OSError):
        return None
    return path if path.is_file() else None


def content_cover_url(obj: models.Model) -> str | None:
    """Absolute public URL for Article/News cover (SITE_URL + /media/…)."""
    cover = getattr(obj, "cover", None)
    if cover is None or not getattr(cover, "name", None):
        return None
    try:
        url = str(cover.url or "").strip()
    except ValueError:
        return None
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    path = url if url.startswith("/") else f"/{url}"
    return f"{settings.SITE_URL.rstrip('/')}{path}"
