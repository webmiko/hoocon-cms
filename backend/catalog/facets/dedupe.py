"""Dedupe AttributeValue rows by normalized attribute name.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import cast

from catalog.models import Attribute, AttributeValue


def _normalize_attr_name(name: str) -> str:
    """Collapse Attribute.name variants for duplicate detection."""
    text = " ".join((name or "").casefold().split())
    text = re.sub(r"\([^)]*\)", "", text).strip()
    # Treat mislabeled «Мощность» with torque semantics as moment.
    if text == "мощность":
        return "крутящий момент"
    if text in {"вид", "вид крана"}:
        return "вид"
    return text


def _attr_prefer_score(name: str) -> int:
    """Higher = keep this Attribute row when collapsing duplicates."""
    low = (name or "").casefold()
    score = 0
    if "крутящий момент" in low:
        score += 20
    if "мощность" in low:
        score -= 10
    if "вид крана" in low:
        score += 5
    # Prefer shorter opaque-slug-free readable names slightly by length.
    score -= min(len(low), 40) // 20
    return score


def dedupe_attribute_values(
    attribute_values: Iterable[AttributeValue],
) -> list[AttributeValue]:
    """Drop duplicate ТТХ rows (same name/value from parallel Tilda attrs).

    Keeps the preferred Attribute when names collide (e.g. «Крутящий момент»
    over mislabeled «Мощность» with the same Нм value).

    Args:
        attribute_values: Prefetched rows with ``attribute`` selected.

    Returns:
        Deduplicated list preserving first-seen order of winners.
    """
    best: dict[tuple[str, str], AttributeValue] = {}
    order: list[tuple[str, str]] = []
    for av in attribute_values:
        attr = cast(Attribute, av.attribute) if av.attribute_id else None
        name = attr.name if attr is not None else ""
        value = " ".join(str(av.value).split())
        key = (_normalize_attr_name(name), value.casefold())
        if key not in best:
            best[key] = av
            order.append(key)
            continue
        current = best[key]
        cur_attr = cast(Attribute, current.attribute) if current.attribute_id else None
        cur_name = cur_attr.name if cur_attr is not None else ""
        if _attr_prefer_score(name) > _attr_prefer_score(cur_name):
            best[key] = av
    return [best[key] for key in order]
