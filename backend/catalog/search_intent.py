"""Catalog free-text search intent (synonym / phrase → category).

Users type natural phrases that are missing from SKU ``search_vector``
(e.g. «кран с приводом» while kit titles say «электрический шаровой кран»).
Detect those intents and map them to the canonical category slug.

Also hosts the keyboard-layout helper: users routinely type queries in the
wrong layout («вф-100» for «DA-100», «ghbdjl» for «привод»); the layout
flip is shared by catalog ``?q=`` and site ``/api/search/``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical slug from series_categories / quiz («Комплект кран + привод»).
KIT_CATEGORY_SLUG = "komplekty"

# Trigram word-similarity floor for typo tolerance («превод» → «привод»).
# Shared by catalog ``?q=`` and site ``/api/search/``; scored per-row over
# a seq scan (tables are small), sku_code additionally uses the ``%`` op.
TRGM_WORD_THRESHOLD = 0.2

# Query length cap for all public search endpoints: FTS + trigram cost
# grows linearly with len(q) (measured ~4s at 6000 chars vs ~0.2s at 6).
SEARCH_Q_MAX_LEN = 100

# Longer phrases first so the most specific match wins.
_KIT_PHRASES: tuple[str, ...] = (
    "электрический шаровой кран с приводом",
    "комплект кран с приводом",
    "комплект кран + привод",
    "шаровой кран с приводом",
    "кран с электроприводом",
    "кран с приводом",
    "кран + привод",
    "кран+привод",
    "кран привод",
    "комплект кран",
    "комплекты",
    "комплект",
)


@dataclass(frozen=True, slots=True)
class CatalogSearchIntent:
    """Resolved free-text intent for catalog / site SKU search.

    Attributes:
        category_slug: Category to force when a phrase matched; else None.
        residual: Query text left after removing the matched phrase (may be empty).
        matched_phrase: Original phrase that matched, for tests/logging.
    """

    category_slug: str | None
    residual: str
    matched_phrase: str | None = None


def normalize_search_query(value: str) -> str:
    """Lowercase, ё→е, collapse ``+``/punctuation into spaces.

    Args:
        value: Raw ``?q=`` text.

    Returns:
        Normalized single-spaced string.
    """
    text = (value or "").casefold().replace("ё", "е")
    text = text.replace("+", " ")
    text = re.sub(r"[^\w\s\-./]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Compile a word-boundary pattern for a normalized multi-word phrase."""
    parts = [re.escape(part) for part in phrase.split() if part]
    body = r"\s+".join(parts)
    return re.compile(rf"(?<!\w){body}(?!\w)", flags=re.UNICODE)


def resolve_catalog_search_intent(value: str) -> CatalogSearchIntent:
    """Map natural kit phrases to ``komplekty``; keep leftover tokens.

    Args:
        value: Raw catalog / site search query.

    Returns:
        Intent with optional category slug and residual query for FTS.
    """
    raw = (value or "").strip()
    if not raw:
        return CatalogSearchIntent(category_slug=None, residual="")

    normalized = normalize_search_query(raw)
    if not normalized:
        return CatalogSearchIntent(category_slug=None, residual="")

    for phrase in _KIT_PHRASES:
        phrase_norm = normalize_search_query(phrase)
        if not phrase_norm:
            continue
        pattern = _phrase_pattern(phrase_norm)
        match = pattern.search(normalized)
        if match is None:
            continue
        residual = pattern.sub(" ", normalized, count=1)
        residual = re.sub(r"\s+", " ", residual).strip()
        return CatalogSearchIntent(
            category_slug=KIT_CATEGORY_SLUG,
            residual=residual,
            matched_phrase=phrase,
        )

    return CatalogSearchIntent(category_slug=None, residual=raw)


# ── Keyboard layout flip (RU ЙЦУКЕН ↔ EN QWERTY) ─────────────────────
# Same physical key produces a Cyrillic or Latin char; map both ways so a
# query typed in the wrong layout still finds codes («вф-100» → «da-100»)
# and words («ghbdjl» → «привод»). Paired by row, order matters.
_LAYOUT_RU_CHARS = "йцукенгшщзхъфывапролджэячсмитьбю.ё"
_LAYOUT_EN_CHARS = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`"

_LAYOUT_TRANSLATION: dict[int, int] = {}
for _ru_char, _en_char in zip(_LAYOUT_RU_CHARS, _LAYOUT_EN_CHARS, strict=True):
    _LAYOUT_TRANSLATION[ord(_ru_char)] = ord(_en_char)
    _LAYOUT_TRANSLATION[ord(_en_char)] = ord(_ru_char)
    _LAYOUT_TRANSLATION[ord(_ru_char.upper())] = ord(_en_char.upper())
    _LAYOUT_TRANSLATION[ord(_en_char.upper())] = ord(_ru_char.upper())


def swap_keyboard_layout(text: str) -> str:
    """Translate every char between RU and EN keyboard layouts.

    Args:
        text: Raw query text typed in either layout.

    Returns:
        Same-length string with each mapped char swapped to the other
        layout; digits, dashes, spaces and unmapped chars stay as is.
    """
    return (text or "").translate(_LAYOUT_TRANSLATION)


def expand_search_variants(raw_q: str) -> tuple[str, ...]:
    """Return query variants: original plus layout-flipped (deduped).

    Args:
        raw_q: Raw ``?q=`` text.

    Returns:
        ``(original,)`` or ``(original, flipped)``; empty tuple for blank
        input. Flipped variant equals the original only for layout-neutral
        strings (digits, dashes) and is then dropped.
    """
    base = (raw_q or "").strip()
    if not base:
        return ()
    flipped = swap_keyboard_layout(base).strip()
    if not flipped or flipped == base:
        return (base,)
    return (base, flipped)
