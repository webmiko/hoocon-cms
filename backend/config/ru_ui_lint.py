"""Lint Russian Admin UI labels for leftover English words.

Used by ``tests/test_admin_i18n.py``. Intentional Latin (brands, acronyms,
env keys, example paths/articles) is allowlisted or stripped before check.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterable
from html import unescape
from typing import Any

# Project apps whose Admin labels must be Russian.
PROJECT_APP_LABELS: frozenset[str] = frozenset(
    {
        "accounts",
        "analytics",
        "catalog",
        "content",
        "crm",
        "leads",
        "redirects",
        "search",
        "sitesettings",
        "social",
        "supportchat",
    },
)

# Brands / stable acronyms acceptable in Russian B2B Admin copy.
LATIN_UI_ALLOWLIST: frozenset[str] = frozenset(
    {
        "id",
        "url",
        "sku",
        "pdf",
        "crm",
        "api",
        "rfq",
        "seo",
        "html",
        "jpeg",
        "png",
        "webp",
        "etl",
        "cdn",
        "smtp",
        "vk",
        "max",
        "ga",
        "og",
        "ip",
        "dn",
        "belimo",
        "telegram",
        "google",
        "analytics",
        "hoocon",
        "cms",
        "tilda",
        "botfather",
    },
)

_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")

# Strip before tokenizing so examples / config keys do not false-positive.
_STRIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"(?<![A-Za-zА-Яа-яЁё])/[A-Za-z0-9_\-./~%]+"),
    # ENV-style keys (must contain underscore): TELEGRAM_BOT_TOKEN.
    re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b"),
    re.compile(r"\bG-[A-Z0-9]{4,}\b", re.IGNORECASE),
    re.compile(r"\bX{4,}\b", re.IGNORECASE),
    re.compile(r"@[A-Za-z0-9_]+"),
    re.compile(r"\bVITE_[A-Za-z0-9_*]*\b", re.IGNORECASE),
    re.compile(r"\.env\b", re.IGNORECASE),
    # Article / series codes with a digit; hyphen is not a word char for \b.
    re.compile(
        r"(?<![A-Za-z0-9_])(?=[A-Za-z0-9.\-/]*\d)[A-Za-z][A-Za-z0-9.\-/]{1,31}"
        r"(?![A-Za-z0-9_])",
    ),
)


def strip_technical_latin(text: str) -> str:
    """Remove URLs, env keys, emails, and article codes from text."""
    out = text or ""
    for pattern in _STRIP_PATTERNS:
        out = pattern.sub(" ", out)
    return out


def unexpected_latin_tokens(text: str) -> list[str]:
    """Return Latin words not in the allowlist (case-preserved, unique order).

    Args:
        text: UI string (verbose_name, help_text, fieldset description, …).

    Returns:
        Unexpected tokens; empty when the string is clean for RU Admin.
    """
    cleaned = strip_technical_latin(text)
    seen: set[str] = set()
    bad: list[str] = []
    for match in _LATIN_WORD.finditer(cleaned):
        raw = match.group(0)
        key = raw.casefold()
        if key in LATIN_UI_ALLOWLIST or key in seen:
            continue
        seen.add(key)
        bad.append(raw)
    return bad


def iter_model_ui_strings(model: type[Any]) -> Iterable[tuple[str, str]]:
    """Yield ``(where, text)`` for model/field verbose names, help, choices."""
    meta = model._meta
    yield f"{meta.label}.verbose_name", str(meta.verbose_name)
    yield f"{meta.label}.verbose_name_plural", str(meta.verbose_name_plural)

    for field in meta.get_fields():
        if not hasattr(field, "verbose_name"):
            continue
        name = getattr(field, "name", getattr(field, "attname", "?"))
        vn = str(getattr(field, "verbose_name", "") or "")
        if vn:
            yield f"{meta.label}.{name}.verbose_name", vn
        ht = str(getattr(field, "help_text", "") or "")
        if ht:
            yield f"{meta.label}.{name}.help_text", ht
        choices = getattr(field, "flatchoices", None) or ()
        for value, label in choices:
            yield f"{meta.label}.{name}.choice[{value!r}]", str(label)


def iter_admin_ui_strings(model_admin: Any, model: type[Any]) -> Iterable[tuple[str, str]]:
    """Yield fieldset titles/descriptions and custom admin verbose names."""
    label = model._meta.label
    for attr in ("verbose_name", "verbose_name_plural"):
        if hasattr(model_admin, attr):
            value = getattr(model_admin, attr)
            if value:
                yield f"admin:{label}.{attr}", str(value)

    fieldsets = getattr(model_admin, "fieldsets", None) or ()
    for index, (title, opts) in enumerate(fieldsets):
        if title:
            yield f"admin:{label}.fieldset[{index}].title", str(title)
        description = (opts or {}).get("description")
        if description:
            yield (
                f"admin:{label}.fieldset[{index}].description",
                str(description),
            )

    app_label = model._meta.app_label
    for name, member in inspect.getmembers(model_admin):
        if name.startswith("_") or not callable(member):
            continue
        origin_module = ""
        for cls in type(model_admin).mro():
            if name in cls.__dict__:
                origin_module = cls.__module__ or ""
                break
        if not (origin_module.startswith("config.") or origin_module.startswith(f"{app_label}.")):
            continue
        for attr in ("short_description", "description"):
            text = getattr(member, attr, None)
            if text and isinstance(text, str):
                yield f"admin:{label}.{name}.{attr}", text
                break


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def extract_html_text_chunks(html: str) -> list[str]:
    """Return visible text fragments from Admin HTML (labels, buttons, headers)."""
    chunks: list[str] = []
    for match in re.finditer(
        r"<(th|label|button|option|title|h[1-6])(?:\s[^>]*)?>([^<]*)</\1>",
        html,
        flags=re.IGNORECASE,
    ):
        text = unescape(_WS_RE.sub(" ", match.group(2)).strip())
        if text:
            chunks.append(text)
    for match in re.finditer(
        r'(?:placeholder|title|aria-label)="([^"]+)"',
        html,
        flags=re.IGNORECASE,
    ):
        text = unescape(_WS_RE.sub(" ", match.group(1)).strip())
        if text:
            chunks.append(text)
    return chunks


def find_unexpected_english_in_html(html: str) -> list[str]:
    """Lint rendered Admin HTML for leftover English UI copy."""
    failures: list[str] = []
    for chunk in extract_html_text_chunks(html):
        bad = unexpected_latin_tokens(chunk)
        if bad:
            failures.append(f"{bad!r} in {chunk!r}")
    return failures
