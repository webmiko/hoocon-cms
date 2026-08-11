"""Resolve catalog SKUs mentioned in article HTML/plain text.

Used for the «Товары из статьи» block on /statyi/<slug>.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from catalog.models import SKU

# Family / edition tokens as they appear in Hoocon copy and the series table.
_MODEL_TOKEN = re.compile(
    r"""
    \b
    (?:
        DA\d{1,3}(?:FU|MU|MQU|EU)(?:24|230)?
        | SA\d{1,3}(?:FU|MU)(?:24|230)?
        | HV[AD](?:\d+)?
        | BV\d{2,3}
    )
    (?:-[A-Za-z0-9]{1,4})?
    \b
    """,
    re.I | re.X,
)

# Compact HV: HVA230S-5QX / HVA-5Q / HVA24-5UQ → family, Nm, speed suffix.
_HV_COMPACT = re.compile(
    r"^(hv[ad])(?:24|230)?s?(\d+)(uq|qx|qa|q|p|f)?$",
    re.I,
)

_TAG = re.compile(r"<[^>]+>")


def extract_model_tokens(text: str) -> list[str]:
    """Return unique model/series tokens found in text (uppercase)."""
    plain = _TAG.sub(" ", text or "")
    seen: set[str] = set()
    out: list[str] = []
    for match in _MODEL_TOKEN.finditer(plain):
        token = match.group(0).upper().replace(" ", "")
        if token in seen:
            continue
        # Skip noise like bare "DATA" false positives — require digit in token.
        if not any(ch.isdigit() for ch in token):
            continue
        seen.add(token)
        out.append(token)
    return out


def _compact_has_token(haystack: str, token: str) -> bool:
    """True if ``token`` is in ``haystack`` without extending into another suffix.

    Prevents ``HVA-5Q`` matching ``HVA-5QX`` and ``DA8MU`` matching ``DA8MQU``.
    Digits after the token are allowed (voltage / edition: ``DA8MU24``).
    """
    if not token or not haystack:
        return False
    start = 0
    while True:
        idx = haystack.find(token, start)
        if idx < 0:
            return False
        end = idx + len(token)
        if end >= len(haystack):
            return True
        nxt = haystack[end]
        if nxt.isdigit():
            return True
        if nxt.isalpha():
            start = idx + 1
            continue
        return True


def _hv_parts(compact: str) -> tuple[str, str, str] | None:
    """Parse compact HV code/token into ``(family, nm, speed)``.

    Speed is ``q`` / ``uq`` / ``qx`` / …; empty string for standard.
    """
    match = _HV_COMPACT.match(compact)
    if match is None:
        return None
    family, nm, speed = match.group(1), match.group(2), match.group(3) or ""
    return family.casefold(), nm, speed.casefold()


def _token_hits_sku(*, needle: str, code: str, slug_compact: str) -> bool:
    """Whether article token ``needle`` matches SKU code or product slug."""
    needle_hv = _hv_parts(needle)
    if needle_hv is not None:
        code_hv = _hv_parts(code)
        if code_hv is not None and code_hv == needle_hv:
            return True
        # Slug often embeds ``hva-5q`` / ``hva-5qx`` without voltage.
        family, nm, speed = needle_hv
        slug_needle = f"{family}{nm}{speed}"
        return _compact_has_token(slug_compact, slug_needle)

    series_core = re.sub(r"(?:24|230)$", "", needle)
    return _compact_has_token(code, needle) or (
        len(series_core) >= 5 and _compact_has_token(slug_compact, series_core)
    )


def mentioned_skus_for_article(
    text: str,
    *,
    limit: int = 8,
) -> list[SKU]:
    """Pick published SKUs that match tokens in the article (one per product).

    Args:
        text: Article title + excerpt + body.
        limit: Max SKUs to return.

    Returns:
        List of SKU instances (may be empty).
    """
    from catalog.models import SKU

    tokens = extract_model_tokens(text)
    if not tokens:
        return []

    # Longer tokens first so DA3FU230-DS beats DA3FU; MQU before MU; UQ before Q.
    tokens_sorted = sorted(tokens, key=len, reverse=True)
    qs = (
        SKU.objects.filter(is_published=True)
        .select_related("product", "product__category")
        .prefetch_related("images")
        .order_by("sku_code")
    )
    picked: list[SKU] = []
    used_products: set[int] = set()

    for token in tokens_sorted:
        if len(picked) >= limit:
            break
        needle = token.casefold().replace("-", "")
        for sku in qs:
            if sku.product_id in used_products:
                continue
            code = sku.sku_code.casefold().replace("-", "").replace(" ", "")
            product_slug = (getattr(sku.product, "slug", None) or "").casefold()
            slug_compact = product_slug.replace("-", "")
            if not _token_hits_sku(
                needle=needle,
                code=code,
                slug_compact=slug_compact,
            ):
                continue
            used_products.add(sku.product_id)
            picked.append(sku)
            break

    return picked[:limit]
