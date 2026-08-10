"""Resolve product slugs for Tilda rows missing `buttonlink`.

Sources (priority):
1. docs/redirects-tproduct-seed.csv — uid → canonical path
2. Store CSV parent `Url` (ЧПУ or /tproduct/… mapped via seed)
3. Live/local sitemap paths matched by title series token
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

_TPRODUCT_UID = re.compile(r"^/?tproduct/(\d+)", re.I)


def load_tproduct_slug_map(seed_csv: Path) -> dict[str, str]:
    """Load uid → slug from redirects-tproduct-seed.csv.

    Args:
        seed_csv: Path to seed CSV with from_path,to_path columns.

    Returns:
        Map of Tilda product uid (digits) → slug without leading slash.
    """
    mapping: dict[str, str] = {}
    if not seed_csv.is_file():
        return mapping
    with seed_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            from_path = (row.get("from_path") or "").strip()
            to_path = (row.get("to_path") or "").strip().lstrip("/")
            match = _TPRODUCT_UID.match(from_path)
            if match and to_path:
                mapping[match.group(1)] = to_path
    return mapping


def slug_from_url(url: str, tproduct_map: dict[str, str]) -> str | None:
    """Derive a catalog slug from a store CSV / sitemap URL."""
    if not url:
        return None
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    match = _TPRODUCT_UID.match(path)
    if match:
        return tproduct_map.get(match.group(1))
    # Already a ЧПУ path
    if path.startswith("tproduct/"):
        return None
    return path


def build_uid_slug_map(
    *,
    seed_csv: Path,
    store_csv: Path | None = None,
) -> dict[str, str]:
    """Combine seed + store CSV parent rows into uid → slug map.

    Args:
        seed_csv: redirects-tproduct-seed.csv
        store_csv: optional Tilda store export (semicolon).

    Returns:
        uid → slug.
    """
    mapping = load_tproduct_slug_map(seed_csv)
    if store_csv is None or not store_csv.is_file():
        return mapping

    with store_csv.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            # Parent product rows have an empty SKU; edition rows carry a code.
            sku = (row.get("SKU") or "").strip()
            if sku:
                continue
            tilda_uid = (row.get("Tilda UID") or "").strip()
            url = (row.get("Url") or "").strip()
            slug = slug_from_url(url, mapping)
            if tilda_uid and slug:
                mapping.setdefault(tilda_uid, slug)
            ext = (row.get("External ID") or "").strip()
            if ext and slug:
                mapping.setdefault(ext, slug)
    return mapping


def apply_slug_to_product(raw: dict, uid_slug_map: dict[str, str]) -> dict:
    """Return a copy of raw product with buttonlink filled when missing.

    Args:
        raw: Tilda product dict.
        uid_slug_map: uid → slug.

    Returns:
        Product dict (possibly patched). Does not mutate input.
    """
    if raw.get("buttonlink"):
        return raw
    uid = str(raw.get("uid") or "").strip()
    slug = uid_slug_map.get(uid)
    if not slug:
        return raw
    patched = dict(raw)
    patched["buttonlink"] = f"/{slug}"
    return patched
