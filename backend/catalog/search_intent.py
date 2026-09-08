"""Catalog free-text search intent (synonym / phrase → category).

Users type natural phrases that are missing from SKU ``search_vector``
(e.g. «кран с приводом» while kit titles say «электрический шаровой кран»).
Detect those intents and map them to the canonical category slug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical slug from series_categories / quiz («Комплект кран + привод»).
KIT_CATEGORY_SLUG = "komplekty"

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
