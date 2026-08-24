"""Documentation hub: family keys, kind inference, deduped ProductFile lists.

Public download center at ``/dokumentaciya`` — not the SKU-nested files API.
Family manuals are attached to many SKUs; list/zip must unique-by-title.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from django.db.models import QuerySet
from django.utils.text import slugify

from catalog.models import SKU, Category, Product, ProductFile
from catalog.validators import sanitize_upload_filename

# DA2MU24-D / DA5MQU230-AS / SA10FU24-DST → DA2MU / DA5MQU / SA10FU
_DA_SA_FAMILY = re.compile(
    r"(?i)^(da|sa)(\d+)(mqu|mu|fu)(?=\d|-|$)",
)
# Family keys themselves: DA2MU / DA5MQU / SA10FU (no voltage/edition).
_DA_SA_FAMILY_KEY = re.compile(r"(?i)^(da|sa)(\d+)(mqu|mu|fu)$")
# HVD24S-5F / HVD230ST-3F → HVD-5F
_HVD_F_FAMILY = re.compile(
    r"(?i)^hvd(?:24|230)s?t?-(\d+)f\b",
)
# HVD24-5 / HVD24S-40 / HVD230-40QX → HVD-5 / HVD-40 / HVD-40QX
_HVD_AIR_FAMILY = re.compile(
    r"(?i)^hvd(?:24|230)s?-(\d+(?:uq|qx|q)?)\b",
)
# HVA24-5 / HVA230S-5Q / HVA24-5UQ → HVA-5 / HVA-5Q / HVA-5UQ
_HVA_FAMILY = re.compile(
    r"(?i)^hva(?:24|230)s?-(\d+(?:uq|qx|q)?)\b",
)
_HV_FAMILY_KEY = re.compile(r"(?i)^(hva|hvd)-(\d+)([a-z]*)$")
_H81_FAMILY = re.compile(r"(?i)^(h81\d{2})\b")
_H81_FAMILY_KEY = re.compile(r"(?i)^h81(\d{2})$")
_BRASS_FAMILY = re.compile(r"(?i)^(8100q?-bv\d+)")
_BRASS_FAMILY_KEY = re.compile(r"(?i)^8100q?-bv(\d+)$")
_H8205_FAMILY = re.compile(r"(?i)^(h8205-lav\d+)")
_H8205_FAMILY_KEY = re.compile(r"(?i)^h8205-lav(\d+)$")
_BR_FAMILY = re.compile(r"(?i)^(br-ml?)\b")
# Natural alphanumeric chunks for titles / leftover keys (DA2 before DA10).
_NATURAL_CHUNK = re.compile(r"(\d+)|(\D+)")
# Mirror catalog.ordering.series_ord_case for hub chips / file groups.
_DA_BODY_ORD: dict[str, int] = {"MU": 10, "MQU": 20, "FU": 50}
_SA_BODY_ORD: dict[str, int] = {"FU": 60, "MU": 70, "MQU": 65}

OTHER_FAMILY = "OTHER"

SERIES_DA = "DA"
SERIES_SA = "SA"
SERIES_HV = "HV"
SERIES_H81 = "H81"
SERIES_BR = "BR"
SERIES_OTHER = "OTHER"

KIND_PASSPORT = "passport"
KIND_MANUAL = "manual"
KIND_CERTIFICATE = "certificate"
KIND_CATALOG = "catalog"
KIND_DATASHEET = "datasheet"
KIND_OTHER = "other"


@dataclass(frozen=True, slots=True)
class DocsFileRow:
    """One deduplicated downloadable document for the hub API."""

    id: int
    title: str
    file_url: str
    kind: str
    family: str
    series: str
    sku_code: str
    sku_slug: str
    product_slug: str
    category_slug: str
    size_bytes: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DocsFamilyMeta:
    """Family group summary for chips and zip links."""

    key: str
    label: str
    series: str
    file_count: int


def doc_family_key(sku_code: str) -> str:
    """Short family key from a catalog SKU code (chips / zip).

    Args:
        sku_code: Edition code, e.g. ``DA2MU24-D``, ``HVD230ST-5F``.

    Returns:
        Uppercase family token, or ``OTHER`` when unrecognized.
    """
    code = (sku_code or "").strip().replace(" ", "")
    if not code:
        return OTHER_FAMILY

    m = _DA_SA_FAMILY.match(code)
    if m is not None:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}".upper()

    m = _HVD_F_FAMILY.match(code)
    if m is not None:
        return f"HVD-{m.group(1)}F"

    m = _HVD_AIR_FAMILY.match(code)
    if m is not None:
        return f"HVD-{m.group(1).upper()}"

    m = _HVA_FAMILY.match(code)
    if m is not None:
        return f"HVA-{m.group(1).upper()}"

    m = _H81_FAMILY.match(code)
    if m is not None:
        return m.group(1).upper()

    m = _BRASS_FAMILY.match(code)
    if m is not None:
        return m.group(1).upper()

    m = _H8205_FAMILY.match(code)
    if m is not None:
        return m.group(1).upper()

    m = _BR_FAMILY.match(code)
    if m is not None:
        return m.group(1).upper()

    return OTHER_FAMILY


def doc_series(family_key: str) -> str:
    """Series chip group for a family key (DA / SA / HV / H81 / BR / OTHER)."""
    key = (family_key or "").strip().upper()
    if key.startswith("DA"):
        return SERIES_DA
    if key.startswith("SA"):
        return SERIES_SA
    if key.startswith("HVA") or key.startswith("HVD"):
        return SERIES_HV
    if key.startswith("H81") or key.startswith("8100") or key.startswith("H8205"):
        return SERIES_H81
    if key.startswith("BR"):
        return SERIES_BR
    return SERIES_OTHER


def natural_doc_sort_parts(text: str) -> tuple[int | str, ...]:
    """Split ``DA10FU`` / titles so digits compare as ints (2 before 10)."""
    parts: list[int | str] = []
    for match in _NATURAL_CHUNK.finditer((text or "").casefold()):
        digits, rest = match.group(1), match.group(2)
        if digits is not None:
            parts.append(int(digits))
        elif rest:
            parts.append(rest)
    return tuple(parts)


def doc_family_sort_key(family_key: str) -> tuple[Any, ...]:
    """Hub order: DA MU→MQU→FU by Нм, then SA FU→MU, HV, valves, OTHER.

    Lexicographic ``DA10FU`` before ``DA2MU`` is wrong; body letters (MU/FU/…)
    stay contiguous like catalog ``series_ord_case``.
    """
    key = (family_key or "").strip().upper()
    if not key or key == OTHER_FAMILY:
        return (9999, 0, "", key)

    m = _DA_SA_FAMILY_KEY.fullmatch(key)
    if m is not None:
        brand = m.group(1).upper()
        nm = int(m.group(2))
        body = m.group(3).upper()
        if brand == "DA":
            body_ord = _DA_BODY_ORD.get(body, 40)
        else:
            body_ord = _SA_BODY_ORD.get(body, 75)
        return (body_ord, nm, body, key)

    m = _HV_FAMILY_KEY.fullmatch(key)
    if m is not None:
        brand = m.group(1).upper()
        nm = int(m.group(2))
        suffix = m.group(3).upper()
        brand_ord = 30 if brand == "HVA" else 40
        return (brand_ord, nm, suffix, key)

    m = _BRASS_FAMILY_KEY.fullmatch(key)
    if m is not None:
        return (80, int(m.group(1)), "", key)

    m = _H81_FAMILY_KEY.fullmatch(key)
    if m is not None:
        return (90, int(m.group(1)), "", key)

    m = _H8205_FAMILY_KEY.fullmatch(key)
    if m is not None:
        return (100, int(m.group(1)), "", key)

    if key == "BR-M":
        return (110, 0, "", key)
    if key == "BR-ML":
        return (110, 1, "", key)

    return (500, 0, "", key)


def doc_file_sort_key(family: str, title: str, file_id: int = 0) -> tuple[Any, ...]:
    """Sort hub rows by family model, then natural title, then id."""
    return (*doc_family_sort_key(family), *natural_doc_sort_parts(title), file_id)


def doc_kind(title: str, file_type: str) -> str:
    """Hub filter kind from ProductFile title + file_type (no migration)."""
    text = (title or "").strip()
    folded = text.casefold()
    # Series datasheets historically mislabeled «Паспорт серии …» — not GOST.
    if folded.startswith("паспорт серии"):
        return KIND_MANUAL
    if folded.startswith("паспорт"):
        return KIND_PASSPORT
    if folded.startswith("инструкция") or folded.startswith("техничка"):
        return KIND_MANUAL
    ft = (file_type or "").strip().casefold()
    if ft == ProductFile.FileType.CERTIFICATE:
        return KIND_CERTIFICATE
    if ft == ProductFile.FileType.CATALOG:
        return KIND_CATALOG
    if ft == ProductFile.FileType.DATASHEET:
        return KIND_DATASHEET
    return KIND_OTHER


def normalize_doc_title(title: str) -> str:
    """Stable dedupe key for shared family manuals."""
    return re.sub(r"\s+", " ", (title or "").strip()).casefold()


def published_files_qs() -> QuerySet[ProductFile]:
    """Published ProductFiles on published SKUs, with catalog FKs loaded."""
    return (
        ProductFile.objects.filter(
            is_published=True,
            sku__is_published=True,
        )
        .select_related(
            "sku",
            "sku__product",
            "sku__product__category",
        )
        .order_by("id")
    )


def _file_size(pf: ProductFile) -> int:
    """Return storage size in bytes; 0 when the file is missing."""
    try:
        if not pf.file:
            return 0
        return int(pf.file.size)
    except (OSError, ValueError, FileNotFoundError):
        return 0


def _file_url(pf: ProductFile, request: Any | None) -> str:
    """Absolute or relative media URL for the PDF."""
    if not pf.file:
        return ""
    url = pf.file.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def dedupe_files_by_family_title(
    files: Iterable[ProductFile],
) -> list[ProductFile]:
    """Keep the lowest-id ProductFile per (family, normalized title)."""
    best: dict[tuple[str, str], ProductFile] = {}
    for pf in files:
        sku = cast(SKU, pf.sku)
        family = doc_family_key(sku.sku_code)
        key = (family, normalize_doc_title(pf.title))
        prev = best.get(key)
        if prev is None or pf.id < prev.id:
            best[key] = pf

    def sort_key(row: ProductFile) -> tuple[Any, ...]:
        sku = cast(SKU, row.sku)
        return doc_file_sort_key(
            doc_family_key(sku.sku_code),
            row.title,
            row.id,
        )

    return sorted(best.values(), key=sort_key)


def row_from_product_file(pf: ProductFile, request: Any | None = None) -> DocsFileRow:
    """Build a hub DTO from a ProductFile (caller supplies deduped rows)."""
    sku = cast(SKU, pf.sku)
    product = cast(Product, sku.product)
    category = cast(Category | None, product.category)
    family = doc_family_key(sku.sku_code)
    category_slug = category.slug if category is not None else ""
    return DocsFileRow(
        id=pf.id,
        title=pf.title,
        file_url=_file_url(pf, request),
        kind=doc_kind(pf.title, pf.file_type),
        family=family,
        series=doc_series(family),
        sku_code=sku.sku_code,
        sku_slug=sku.slug,
        product_slug=product.slug,
        category_slug=category_slug,
        size_bytes=_file_size(pf),
        updated_at=pf.updated_at,
    )


def filter_doc_rows(
    rows: list[DocsFileRow],
    *,
    q: str = "",
    series: str = "",
    kind: str = "",
    family: str = "",
) -> list[DocsFileRow]:
    """Apply hub query filters (case-insensitive substring / exact chips)."""
    out = rows
    series_f = series.strip().upper()
    kind_f = kind.strip().casefold()
    family_f = family.strip().upper()
    q_f = q.strip().casefold()

    if series_f:
        out = [r for r in out if r.series == series_f]
    if kind_f:
        out = [r for r in out if r.kind.casefold() == kind_f]
    if family_f:
        out = [r for r in out if r.family == family_f]
    if q_f:
        out = [
            r
            for r in out
            if q_f in r.title.casefold()
            or q_f in r.sku_code.casefold()
            or q_f in r.family.casefold()
            or q_f in r.product_slug.casefold()
        ]
    return out


def build_family_metas(rows: list[DocsFileRow]) -> list[DocsFamilyMeta]:
    """Aggregate unique file counts per family (model + Nm order)."""
    counts: dict[str, int] = {}
    series_by: dict[str, str] = {}
    for row in rows:
        counts[row.family] = counts.get(row.family, 0) + 1
        series_by[row.family] = row.series
    metas: list[DocsFamilyMeta] = []
    for key in sorted(counts.keys(), key=doc_family_sort_key):
        metas.append(
            DocsFamilyMeta(
                key=key,
                label=key,
                series=series_by[key],
                file_count=counts[key],
            ),
        )
    return metas


def collect_hub_payload(
    *,
    request: Any | None = None,
    q: str = "",
    series: str = "",
    kind: str = "",
    family: str = "",
) -> dict[str, Any]:
    """Deduped files + family metas for ``GET /api/catalog/docs/``."""
    unique = dedupe_files_by_family_title(published_files_qs())
    rows = [row_from_product_file(pf, request) for pf in unique]
    filtered = filter_doc_rows(
        rows,
        q=q,
        series=series,
        kind=kind,
        family=family,
    )
    filtered = sorted(
        filtered,
        key=lambda r: doc_file_sort_key(r.family, r.title, r.id),
    )
    # Family chips always reflect the filtered file set.
    families = build_family_metas(filtered)
    return {
        "families": [
            {
                "key": f.key,
                "label": f.label,
                "series": f.series,
                "file_count": f.file_count,
                "zip_path": f"/api/catalog/docs/families/{f.key}/zip/",
            }
            for f in families
        ],
        "files": [
            {
                "id": r.id,
                "title": r.title,
                "file": r.file_url,
                "kind": r.kind,
                "family": r.family,
                "series": r.series,
                "sku_code": r.sku_code,
                "sku_slug": r.sku_slug,
                "product_slug": r.product_slug,
                "category_slug": r.category_slug,
                "size_bytes": r.size_bytes,
                "updated_at": r.updated_at.isoformat().replace("+00:00", "Z"),
            }
            for r in filtered
        ],
    }


def unique_product_files_for_family(family_key: str) -> list[ProductFile]:
    """Deduped published ProductFiles belonging to ``family_key``."""
    wanted = family_key.strip().upper()
    if not wanted:
        return []
    candidates: list[ProductFile] = []
    for pf in published_files_qs():
        if doc_family_key(cast(SKU, pf.sku).sku_code) == wanted:
            candidates.append(pf)
    return dedupe_files_by_family_title(candidates)


def zip_entry_name(title: str, file_id: int) -> str:
    """Safe PDF basename inside a family archive."""
    base = slugify(title, allow_unicode=False) or f"doc-{file_id}"
    safe = sanitize_upload_filename(f"{base}.pdf")
    if not safe.lower().endswith(".pdf"):
        safe = f"{safe}.pdf"
    return safe


def family_zip_etag(files: list[ProductFile]) -> str:
    """Weak ETag from ids + updated_at + count."""
    raw = f"{len(files)}:" + "|".join(f"{pf.id}:{pf.updated_at.isoformat()}" for pf in files)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_family_zip_bytes(files: list[ProductFile]) -> bytes:
    """Build an in-memory zip of unique family PDFs."""
    buf = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pf in files:
            name = zip_entry_name(pf.title, pf.id)
            if name in used_names:
                stem = name[:-4] if name.lower().endswith(".pdf") else name
                name = f"{stem}-{pf.id}.pdf"
            used_names.add(name)
            try:
                with pf.file.open("rb") as src:
                    zf.writestr(name, src.read())
            except (OSError, ValueError, FileNotFoundError):
                continue
    return buf.getvalue()
