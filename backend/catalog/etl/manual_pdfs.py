"""Attach local instruction PDFs to matching catalog SKUs.

Source of truth for manuals: repo symlink ``_инструкции-pdf``
(Yandex Disk «Интскрукции по эксплуатации/PDF»).

Filename conventions (DAFU)::

    da5fu-d:ds.pdf      → DA5FU …-D / …-DS (24 В and 230 В)
    da5fu24-a:as.pdf    → DA5FU24-A / DA5FU24-AS

SAFU (fire/smoke)::

    sa3fu-ds_dst.pdf    → SA3FU …-DS / …-DST (24 В and 230 В)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.models import SKU, ProductFile

logger = logging.getLogger(__name__)

# Trailing NBSP / spaces appear in some Disk exports (e.g. da5fu-d:ds\\xa0.pdf).
_ON_OFF_STEM = re.compile(r"(?i)^da(?P<nm>\d+)fu-d[:_\-]ds?$")
_MOD_24_STEM = re.compile(r"(?i)^da(?P<nm>\d+)fu24-a[:_\-]as?$")
_DAFU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)fu")
_SAFU_STEM = re.compile(r"(?i)^sa(?P<nm>\d+)fu(?:-ds[_-]?dst)?$")
_SAFU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)fu")


@dataclass(frozen=True, slots=True)
class ManualMatch:
    """One PDF mapped onto a set of SKU codes."""

    path: Path
    torque_nm: int
    kind: str  # "on_off" | "modulating_24"
    sku_codes: tuple[str, ...]


def default_manuals_dir(repo_root: Path | None = None) -> Path:
    """Resolve ``_инструкции-pdf`` next to the Django project root.

    Args:
        repo_root: Optional override (defaults to parents of ``backend/``).

    Returns:
        Absolute path to the manuals directory (may not exist yet).
    """
    if repo_root is None:
        # backend/catalog/etl/manual_pdfs.py → repo root
        repo_root = Path(__file__).resolve().parents[3]
    return (repo_root / "_инструкции-pdf").resolve()


def normalize_manual_stem(filename: str) -> str:
    """Strip extension and Disk artefacts from a PDF basename."""
    stem = Path(filename).name
    if stem.casefold().endswith(".pdf"):
        stem = stem[:-4]
    return stem.replace("\xa0", "").strip()


def parse_manual_stem(stem: str) -> tuple[int, str] | None:
    """Parse a normalized stem into ``(torque_nm, kind)``.

    Args:
        stem: Basename without ``.pdf``.

    Returns:
        ``(nm, "on_off"|"modulating_24")`` or None if not a DAFU manual.
    """
    clean = normalize_manual_stem(stem)
    m = _ON_OFF_STEM.fullmatch(clean)
    if m:
        return int(m.group("nm")), "on_off"
    m = _MOD_24_STEM.fullmatch(clean)
    if m:
        return int(m.group("nm")), "modulating_24"
    return None


def sku_codes_for_manual(kind: str, torque_nm: int, sku_codes: list[str]) -> list[str]:
    """Filter catalog SKU codes that a DAFU manual covers.

    Args:
        kind: ``on_off`` or ``modulating_24``.
        torque_nm: Family torque (3, 5, 10, …).
        sku_codes: Candidate SKU codes (any series).

    Returns:
        Matching codes preserving input order.
    """
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        m = _DAFU_CODE.match(compact)
        if m is None or int(m.group("nm")) != torque_nm:
            continue
        if kind == "on_off":
            if compact.endswith("-ds") or compact.endswith("-d"):
                out.append(code)
        elif kind == "modulating_24":
            if compact.startswith(f"da{torque_nm}fu24-") and (compact.endswith("-as") or compact.endswith("-a")):
                out.append(code)
    return out


def discover_dafu_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan ``manuals_dir`` for DAFU PDFs and map them to SKU codes.

    Args:
        manuals_dir: Directory with ``*.pdf``.
        sku_codes: Optional explicit code list; otherwise load published DAFU.

    Returns:
        ``(matches, warnings)`` — unmatched PDFs / empty mappings as warnings.
    """
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__iregex=r"(?i)^da[0-9]+fu").values_list(
                "sku_code",
                flat=True,
            ),
        )
    matches: list[ManualMatch] = []
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return matches, warnings

    for path in sorted(manuals_dir.glob("*.pdf")):
        parsed = parse_manual_stem(path.name)
        if parsed is None:
            if re.search(r"(?i)da\d+fu", path.name):
                warnings.append(f"unrecognized DAFU filename: {path.name!r}")
            continue
        torque_nm, kind = parsed
        codes = sku_codes_for_manual(kind, torque_nm, sku_codes)
        if not codes:
            warnings.append(
                f"no SKU for {path.name!r} (nm={torque_nm} kind={kind})",
            )
            continue
        matches.append(
            ManualMatch(
                path=path,
                torque_nm=torque_nm,
                kind=kind,
                sku_codes=tuple(codes),
            ),
        )
    return matches, warnings


def _storage_basename(path: Path) -> str:
    """Safe PDF basename for FileField storage (no ``:`` / NBSP)."""
    stem = normalize_manual_stem(path.name).replace(":", "-")
    return f"{stem}.pdf"


def _manual_title(match: ManualMatch) -> str:
    label = "D/DS" if match.kind == "on_off" else "A/AS (24 В)"
    return f"Инструкция DA{match.torque_nm}FU ({label})"


def attach_dafu_manuals(
    manuals_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update ProductFile datasheets for DAFU SKUs from local PDFs.

    Idempotent by ``(sku, title)``: existing rows keep the file refreshed when
    the source PDF differs in size; missing rows are created.

    Args:
        manuals_dir: Path to ``_инструкции-pdf``.
        dry_run: When True, compute the plan without writing.

    Returns:
        Summary counters and warning list.
    """
    matches, warnings = discover_dafu_manuals(manuals_dir)
    summary: dict[str, Any] = {
        "manuals": len(matches),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "warnings": warnings,
        "dry_run": dry_run,
        "by_sku": {},
    }
    if not matches:
        return summary

    code_to_sku = {
        s.sku_code.casefold(): s
        for s in SKU.objects.filter(
            sku_code__in=[c for m in matches for c in m.sku_codes],
        )
    }

    with transaction.atomic():
        for match in matches:
            payload = match.path.read_bytes()
            title = _manual_title(match)
            basename = _storage_basename(match.path)
            for code in match.sku_codes:
                sku = code_to_sku.get(code.casefold())
                if sku is None:
                    warnings.append(f"SKU missing in DB: {code}")
                    continue
                existing = ProductFile.objects.filter(sku=sku, title=title).first()
                if dry_run:
                    summary["by_sku"].setdefault(code, []).append(title)
                    if existing is None:
                        summary["created"] += 1
                    else:
                        summary["updated"] += 1
                    continue
                if existing is None:
                    pf = ProductFile(
                        sku=sku,
                        title=title,
                        file_type=ProductFile.FileType.DATASHEET,
                        is_published=True,
                        sort_order=0,
                    )
                    pf.file.save(basename, ContentFile(payload), save=True)
                    summary["created"] += 1
                    logger.info(
                        "manual_pdf_attached sku=%s title=%s",
                        sku.sku_code,
                        title,
                    )
                else:
                    # Refresh bytes when the source PDF changed.
                    current_size = existing.file.size if existing.file else 0
                    if current_size != len(payload):
                        existing.file.save(basename, ContentFile(payload), save=True)
                        summary["updated"] += 1
                    else:
                        summary["skipped"] += 1
                summary["by_sku"].setdefault(code, []).append(title)
        if dry_run:
            transaction.set_rollback(True)

    summary["warnings"] = warnings
    return summary


def ensure_dafu_spring_category(*, dry_run: bool = False) -> dict[str, int]:
    """Move DAFU products under the spring-return category (Tilda / series).

    Prefers the Tilda child slug when present; otherwise the series-spec slug.

    Args:
        dry_run: Plan only.

    Returns:
        ``{"moved": n, "already": n}``.
    """
    from catalog.models import Category, Product

    preferred = (
        "elektroprivod-vozdushniy-s-vozvratnoy-pruzhinoy",
        "elektroprivody-s-pruzhinnym-vozvratom",
    )
    target: Category | None = None
    for slug in preferred:
        target = Category.objects.filter(slug=slug).first()
        if target is not None:
            break
    if target is None:
        target = Category.objects.create(
            slug="elektroprivody-s-pruzhinnym-vozvratom",
            name="Электроприводы с пружинным возвратом",
        )

    moved = 0
    already = 0
    qs = Product.objects.filter(slug__icontains="dafu")
    for product in qs:
        if product.category_id == target.pk:
            already += 1
            continue
        moved += 1
        if not dry_run:
            product.category = target
            product.save(update_fields=["category"])
    return {"moved": moved, "already": already, "category": target.slug}


def parse_safu_manual_stem(stem: str) -> int | None:
    """Parse ``sa5fu-ds_dst`` → ``5``, or None if not a SAFU manual."""
    clean = normalize_manual_stem(stem)
    match = _SAFU_STEM.fullmatch(clean)
    if match is None:
        return None
    return int(match.group("nm"))


def sku_codes_for_safu_manual(torque_nm: int, sku_codes: list[str]) -> list[str]:
    """Filter catalog SKU codes that a SAFU DS/DST manual covers."""
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        match = _SAFU_CODE.match(compact)
        if match is None or int(match.group("nm")) != torque_nm:
            continue
        if compact.endswith("-ds") or compact.endswith("-dst"):
            out.append(code)
    return out


def discover_safu_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan ``manuals_dir`` for SAFU PDFs and map them to SKU codes."""
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__iregex=r"(?i)^sa[0-9]+fu").values_list(
                "sku_code",
                flat=True,
            ),
        )
    matches: list[ManualMatch] = []
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return matches, warnings

    for path in sorted(manuals_dir.glob("*.pdf")):
        torque_nm = parse_safu_manual_stem(path.name)
        if torque_nm is None:
            if re.search(r"(?i)sa\d+fu", path.name):
                warnings.append(f"unrecognized SAFU filename: {path.name!r}")
            continue
        codes = sku_codes_for_safu_manual(torque_nm, sku_codes)
        if not codes:
            warnings.append(f"no SKU for {path.name!r} (nm={torque_nm} safu)")
            continue
        matches.append(
            ManualMatch(
                path=path,
                torque_nm=torque_nm,
                kind="safu_ds_dst",
                sku_codes=tuple(codes),
            ),
        )
    return matches, warnings


def attach_safu_manuals(
    manuals_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update ProductFile datasheets for SAFU SKUs from local PDFs."""
    matches, warnings = discover_safu_manuals(manuals_dir)
    summary: dict[str, Any] = {
        "manuals": len(matches),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "warnings": warnings,
        "dry_run": dry_run,
        "by_sku": {},
    }
    if not matches:
        return summary

    code_to_sku = {
        s.sku_code.casefold(): s
        for s in SKU.objects.filter(
            sku_code__in=[c for m in matches for c in m.sku_codes],
        )
    }

    with transaction.atomic():
        for match in matches:
            payload = match.path.read_bytes()
            title = f"Инструкция SA{match.torque_nm}FU (DS/DST)"
            basename = _storage_basename(match.path)
            for code in match.sku_codes:
                sku = code_to_sku.get(code.casefold())
                if sku is None:
                    warnings.append(f"SKU missing in DB: {code}")
                    continue
                existing = ProductFile.objects.filter(sku=sku, title=title).first()
                if dry_run:
                    summary["by_sku"].setdefault(code, []).append(title)
                    if existing is None:
                        summary["created"] += 1
                    else:
                        summary["updated"] += 1
                    continue
                if existing is None:
                    pf = ProductFile(
                        sku=sku,
                        title=title,
                        file_type=ProductFile.FileType.DATASHEET,
                        is_published=True,
                        sort_order=0,
                    )
                    pf.file.save(basename, ContentFile(payload), save=True)
                    summary["created"] += 1
                    logger.info(
                        "manual_pdf_attached sku=%s title=%s",
                        sku.sku_code,
                        title,
                    )
                else:
                    current_size = existing.file.size if existing.file else 0
                    if current_size != len(payload):
                        existing.file.save(basename, ContentFile(payload), save=True)
                        summary["updated"] += 1
                    else:
                        summary["skipped"] += 1
                summary["by_sku"].setdefault(code, []).append(title)
        if dry_run:
            transaction.set_rollback(True)

    summary["warnings"] = warnings
    return summary
