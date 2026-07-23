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

    # Longer tokens first so DA3FU230-DS beats DA3FU.
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
            # Exact / prefix match on sku_code, or series in product slug.
            series_core = re.sub(r"(?:24|230)$", "", needle)
            hit = (
                code.startswith(needle)
                or needle.startswith(code)
                or (len(series_core) >= 5 and series_core in code)
                or (len(series_core) >= 5 and series_core in product_slug.replace("-", ""))
            )
            if not hit:
                continue
            used_products.add(sku.product_id)
            picked.append(sku)
            break

    return picked[:limit]
