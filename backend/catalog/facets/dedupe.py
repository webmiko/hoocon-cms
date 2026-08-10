"""Dedupe AttributeValue rows by normalized attribute name.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import cast

from catalog.models import Attribute, AttributeValue

# Canonical Belimo Y/U signal slugs + legacy Tilda aliases → one dedupe bucket.
_SIGNAL_SLUG_BUCKET: dict[str, str] = {
    "control-signal": "control-signal",
    "control-signal-y": "control-signal",
    "feedback-signal": "feedback-signal",
    "feedback-signal-u": "feedback-signal",
}


def _normalize_attr_name(name: str) -> str:
    """Collapse Attribute.name variants for duplicate detection."""
    text = " ".join((name or "").casefold().split())
    text = re.sub(r"\([^)]*\)", "", text).strip()
    # Treat mislabeled «Мощность» with torque semantics as moment.
    if text == "мощность":
        return "крутящий момент"
    if text in {"вид", "вид крана"}:
        return "вид"
    # Legacy Tilda «Управляющий сигнал Y» vs canon «Упр. сигнал Y».
    if text in {"управляющий сигнал y", "упр. сигнал y", "упр сигнал y"}:
        return "упр. сигнал y"
    if text in {"управляющий сигнал u", "упр. сигнал u", "упр сигнал u"}:
        return "упр. сигнал u"
    return text


def _dedupe_key(name: str, slug: str, value: str) -> tuple[str, str]:
    """Build collapse key: prefer Y/U slug bucket, else normalized name."""
    bucket = _SIGNAL_SLUG_BUCKET.get((slug or "").casefold())
    if bucket is not None:
        return (f"slug:{bucket}", value.casefold())
    return (_normalize_attr_name(name), value.casefold())


def _attr_prefer_score(name: str, *, slug: str = "") -> int:
    """Higher = keep this Attribute row when collapsing duplicates."""
    low = (name or "").casefold()
    slug_low = (slug or "").casefold()
    score = 0
    if "крутящий момент" in low:
        score += 20
    if "мощность" in low:
        score -= 10
    if "вид крана" in low:
        score += 5
    # Prefer canonical Belimo Y/U slugs over legacy *-y / *-u aliases.
    if slug_low in {"control-signal", "feedback-signal"}:
        score += 15
    if slug_low in {"control-signal-y", "feedback-signal-u"}:
        score -= 5
    # Prefer shorter opaque-slug-free readable names slightly by length.
    score -= min(len(low), 40) // 20
    return score


def dedupe_attribute_values(
    attribute_values: Iterable[AttributeValue],
) -> list[AttributeValue]:
    """Drop duplicate ТТХ rows (same name/value from parallel Tilda attrs).

    Keeps the preferred Attribute when names collide (e.g. «Крутящий момент»
    over mislabeled «Мощность» with the same Нм value). Also collapses
    legacy ``control-signal-y`` / ``feedback-signal-u`` onto canonical Y/U
    slugs when values match.

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
        slug = attr.slug if attr is not None else ""
        value = " ".join(str(av.value).split())
        key = _dedupe_key(name, slug, value)
        if key not in best:
            best[key] = av
            order.append(key)
            continue
        current = best[key]
        cur_attr = cast(Attribute, current.attribute) if current.attribute_id else None
        cur_name = cur_attr.name if cur_attr is not None else ""
        cur_slug = cur_attr.slug if cur_attr is not None else ""
        if _attr_prefer_score(name, slug=slug) > _attr_prefer_score(cur_name, slug=cur_slug):
            best[key] = av
    return [best[key] for key in order]
