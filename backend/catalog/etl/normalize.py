"""Normalize + validate raw Tilda records into typed dataclasses.

Pure functions — no Django ORM. Bad rows raise QuarantineError with a reason
and the offending payload, so the loader can write them to a quarantine CSV.

Spec: docs/data-quality-etl.md §4.1 (SKU/атрибуты gates).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

# Reserved keys in Tilda edition dict that are NOT attributes.
_EDITION_RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "uid",
        "externalid",
        "sku",
        "price",
        "priceold",
        "quantity",
        "img",
    },
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Typo → canonical product slugs (Tilda index → Hoocon CMS).
# Spec: docs/seo-url-migration.md §2.1.1; seed docs/redirects-slug-typo-seed.csv.
PRODUCT_SLUG_REMAP: dict[str, str] = {
    "privod-protivipozharniy-3nm": "privod-protivopozharniy-3nm",
    "privod-vozdushniy-bezpruzhini-uskorenniy-hva-q-5nm": ("privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-5nm"),
}


def _sku_code_segment(sku_code: str) -> str:
    """Normalize sku_code into a slug-safe path segment."""
    segment = re.sub(r"[^a-z0-9]+", "-", sku_code.lower()).strip("-")
    return segment or "sku"


class QuarantineError(ValueError):
    """Raised when a raw row fails validation; payload kept for CSV logging.

    Attributes:
        reason: short human-readable reason (Russian, for ops).
        payload: the offending raw record (dict).
    """

    def __init__(self, reason: str, payload: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.payload = payload


@dataclass(frozen=True)
class NormalizedCategory:
    """Validated category record ready for ORM load."""

    tilda_id: int
    name: str
    slug: str
    parent_id: int | None


@dataclass(frozen=True)
class NormalizedAttribute:
    """One attribute value on a SKU (EAV)."""

    title: str
    value: str


@dataclass(frozen=True)
class NormalizedSKU:
    """Validated SKU record ready for ORM load."""

    sku_code: str
    slug: str
    name: str
    price: Decimal | None
    attributes: tuple[NormalizedAttribute, ...]
    description: str = ""


@dataclass(frozen=True)
class NormalizedProduct:
    """Validated product record ready for ORM load."""

    tilda_uid: str
    name: str
    slug: str
    description: str
    category_id: int | None
    skus: tuple[NormalizedSKU, ...] = field(default_factory=tuple)


def normalize_slug(buttonlink: str) -> str:
    """Strip leading slash, fix known typo slugs, validate `[a-z0-9-]+`.

    Args:
        buttonlink: Tilda buttonlink, e.g. '/privod-...-3nm'.

    Returns:
        Canonical slug without leading slash.

    Raises:
        QuarantineError: empty or invalid format.
    """
    if buttonlink is None:
        raise QuarantineError("empty slug", {"buttonlink": buttonlink})
    raw = str(buttonlink).strip()
    if not raw:
        raise QuarantineError("empty slug", {"buttonlink": buttonlink})
    slug = raw.lstrip("/")
    if not slug or not _SLUG_PATTERN.match(slug):
        raise QuarantineError(
            f"invalid slug format: {slug!r}",
            {"buttonlink": buttonlink},
        )
    return PRODUCT_SLUG_REMAP.get(slug, slug)


def _slugify_ru(text: str) -> str:
    """Slugify a Russian name to [a-z0-9-]+ (translit + cleanup).

    Args:
        text: Russian name, e.g. 'Электропривод воздушной заслонки'.

    Returns:
        Slug, e.g. 'elektroprivod-vozdushnoy-zaslonki'.
    """
    translit = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    text = text.lower().strip()
    # Collapse the Russian ending "ый" → "iy" (avoids doubled 'y' in slugs).
    text = text.replace("ый", "iy")
    out: list[str] = []
    for ch in text:
        if ch in translit:
            out.append(translit[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
    slug = "".join(out)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug or not _SLUG_PATTERN.match(slug):
        raise QuarantineError(f"cannot slugify category: {text!r}", {"name": text})
    return slug


def normalize_category(
    cid: int,
    name: str,
    parent_id: int | None,
) -> NormalizedCategory:
    """Build a NormalizedCategory with a slug derived from the Russian name.

    Args:
        cid: Tilda category id (stable across imports).
        name: Russian category name.
        parent_id: Tilda parent category id or None for top-level.

    Returns:
        NormalizedCategory.

    Raises:
        QuarantineError: if name cannot be slugified.
    """
    if not name or not name.strip():
        raise QuarantineError("empty category name", {"id": cid, "name": name})
    slug = _slugify_ru(name)
    return NormalizedCategory(tilda_id=cid, name=name.strip(), slug=slug, parent_id=parent_id)


def _parse_price(raw: Any) -> Decimal | None:
    """Parse edition price: empty → None; numeric string → Decimal.

    Args:
        raw: Tilda edition price (usually '' or null).

    Returns:
        Decimal or None.

    Raises:
        QuarantineError: if non-empty string is not a number.
    """
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return Decimal(str(raw).strip())
    except InvalidOperation as exc:
        raise QuarantineError(
            f"invalid price: {raw!r}",
            {"price": raw},
        ) from exc


def _normalize_edition(
    edition: dict[str, Any],
    product_slug: str,
    product_name: str,
    product_description: str = "",
    product_attributes: tuple[NormalizedAttribute, ...] = (),
) -> NormalizedSKU:
    """Build a NormalizedSKU from a Tilda edition dict.

    Args:
        edition: raw edition dict.
        product_slug: parent product slug (for SKU slug derivation).
        product_name: parent product name (for SKU display name).
        product_description: plain-text description copied onto each SKU.
        product_attributes: product-level characteristics merged into EAV.

    Returns:
        NormalizedSKU.

    Raises:
        QuarantineError: empty sku_code, invalid slug derivation, bad price.
    """
    sku_code = str(edition.get("sku") or "").strip()
    if not sku_code:
        raise QuarantineError("empty sku_code", {"edition": edition})

    sku_slug = f"{product_slug}-{_sku_code_segment(sku_code)}"
    if not _SLUG_PATTERN.match(sku_slug):
        raise QuarantineError(
            f"invalid derived sku slug: {sku_slug!r}",
            {"edition": edition, "product_slug": product_slug},
        )

    price = _parse_price(edition.get("price"))

    from catalog.etl.tech_copy import (
        normalize_control_attribute_value,
        normalize_tech_copy,
    )

    attrs: list[NormalizedAttribute] = list(product_attributes)
    seen_titles = {a.title.lower() for a in attrs}
    for key, value in edition.items():
        if key in _EDITION_RESERVED_KEYS:
            continue
        if key.startswith("__"):
            continue
        value_str = str(value).strip() if value is not None else ""
        if not value_str:
            continue
        title = str(key).strip()
        if title.lower() in seen_titles:
            # Edition-specific value overrides product-level characteristic.
            attrs = [a for a in attrs if a.title.lower() != title.lower()]
        if "управл" in title.casefold():
            value_str = normalize_control_attribute_value(value_str)
        else:
            value_str = normalize_tech_copy(value_str)
        attrs.append(NormalizedAttribute(title=title, value=value_str))
        seen_titles.add(title.lower())

    return NormalizedSKU(
        sku_code=sku_code,
        slug=sku_slug,
        name=f"{product_name} ({sku_code})",
        price=price,
        attributes=tuple(attrs),
        description=normalize_tech_copy(product_description),
    )


def normalize_product(raw: dict[str, Any]) -> NormalizedProduct:
    """Build a NormalizedProduct from a raw Tilda product dict.

    Args:
        raw: raw product dict from extract_products.

    Returns:
        NormalizedProduct with nested SKUs + attributes.

    Raises:
        QuarantineError: empty buttonlink, invalid slug, bad editions.
    """
    payload_for_error = {"uid": raw.get("uid"), "title": raw.get("title")}

    buttonlink = raw.get("buttonlink") or ""
    try:
        slug = normalize_slug(buttonlink)
    except QuarantineError as exc:
        raise QuarantineError(exc.reason, {**payload_for_error, **exc.payload}) from exc

    name = str(raw.get("title") or "").strip()
    if not name:
        raise QuarantineError("empty product title", payload_for_error)

    from catalog.etl.html_text import html_to_text

    description = html_to_text(str(raw.get("descr") or ""))
    text_extra = html_to_text(str(raw.get("text") or ""))
    if text_extra and text_extra not in description:
        description = f"{description}\n\n{text_extra}".strip() if description else text_extra

    product_attrs: list[NormalizedAttribute] = []
    characteristics = raw.get("characteristics") or []
    if isinstance(characteristics, str):
        try:
            import json

            characteristics = json.loads(characteristics)
        except (json.JSONDecodeError, TypeError):
            characteristics = []
    if isinstance(characteristics, list):
        for item in characteristics:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            value = str(item.get("value") or "").strip()
            if title and value:
                product_attrs.append(NormalizedAttribute(title=title, value=value))

    partuids_raw = raw.get("partuids") or []
    # Tilda sometimes stores partuids as a JSON-encoded string instead of a
    # list. Normalize to a list of ints before picking the leaf category.
    if isinstance(partuids_raw, str):
        try:
            import json

            partuids_raw = json.loads(partuids_raw)
        except (json.JSONDecodeError, TypeError):
            partuids_raw = []
    if not isinstance(partuids_raw, list):
        partuids_raw = []
    # Tilda lists the deepest subcategory FIRST in partuids, then its parent.
    # We pick the first id — that's the leaf category for this product.
    category_id: int | None = None
    if partuids_raw:
        try:
            category_id = int(partuids_raw[0])
        except (TypeError, ValueError):
            category_id = None

    editions = raw.get("editions") or []
    skus: list[NormalizedSKU] = []
    for edition in editions:
        if not isinstance(edition, dict):
            continue
        try:
            skus.append(
                _normalize_edition(
                    edition,
                    slug,
                    name,
                    product_description=description,
                    product_attributes=tuple(product_attrs),
                ),
            )
        except QuarantineError as exc:
            raise QuarantineError(
                f"edition rejected: {exc.reason}",
                {**payload_for_error, "edition": edition, **exc.payload},
            ) from exc

    return NormalizedProduct(
        tilda_uid=str(raw.get("uid") or ""),
        name=name,
        slug=slug,
        description=description,
        category_id=category_id,
        skus=tuple(skus),
    )
