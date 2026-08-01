"""Attach local instruction PDFs to matching catalog SKUs.

Source of truth for manuals: repo symlink ``_инструкции-pdf``
(Yandex Disk «Интскрукции по эксплуатации/PDF»), with language
subfolders ``RU/`` (translated) and ``EN/`` (still English). Discovery
scans both (RU first) plus any leftover flat files in the root.

Filename conventions (DAFU)::

    da5fu-d:ds.pdf      → DA5FU …-D / …-DS (24 В and 230 В)
    da5fu24-a:as.pdf    → DA5FU24-A / DA5FU24-AS

SAFU (fire/smoke)::

    sa3fu-ds_dst.pdf                         → SA3FU …-DS / …-DST
    SA3FU-DS_DST — руководство (RU).pdf      → same (RU preferred over EN)

DAMU / DAMQU (no spring, English manuals)::

    da2mu-a_as.pdf                 → DA2MU …-A / …-AS (24 В and 230 В)
    da2mu-d_ds.pdf                 → DA2MU …-D / …-DS
    da4_6mu-a_as.pdf               → DA4MU + DA6MU …-A / …-AS
    da8_16_24_32mu24-d_ds.pdf      → DA8/16/24/32MU24 …-D / …-DS
    da8_16_24mqu230-a_as.pdf       → DA8MQU230 …-A / …-AS (…16/24 if present)

SAMU (smoke, no spring)::

    sa10mu-ds_dst.pdf                        → SA10MU …-DS / …-DST (EN)
    SA10MU-DS — руководство (RU).pdf         → SA10MU …-DS only (RU preferred)

HVD fire/smoke F-series (spring return; not air HVD-5)::

    hvd-3f-s_st.pdf                → HVD24/230 S/ST-3F
    hvd-5f-s_st.pdf                → HVD24/230 S/ST-5F

HVA modulating air (no spring; ASCII stems after rename)::

    hva-5.pdf / HVA-5 instruction.pdf → HVA24/230[S]-5
    hva-5q.pdf                        → HVA24/230[S]-5Q
    hva-10.pdf / hva-10q.pdf / …      → matching HVA* codes when present
    hva-5uq.pdf                       → special (warn if no SKU)
    # hva-*p.pdf — Chinese spring HVA-P; out of RF catalog (skip)
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
# sa5fu-ds_dst | SA5FU-DS_DST | sa5fu-ds (RU DS-only)
_SAFU_STEM = re.compile(r"(?i)^sa(?P<nm>\d+)fu(?:-ds(?P<dst>[_-]?dst)?)?$")
_SAFU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)fu")
# da2mu-a_as | da4_6mu-d_ds | da8_16_24_32mu24-a_as | da8_16_24mqu230-d_ds
_DAMU_STEM = re.compile(
    r"(?i)^da(?P<nms>\d+(?:_\d+)*)mu(?P<volt>24|230)?-(?P<kind>a_as|d_ds)$",
)
_DAMQU_STEM = re.compile(
    r"(?i)^da(?P<nms>\d+(?:_\d+)*)mqu(?P<volt>24|230)?-(?P<kind>a_as|d_ds)$",
)
_DAMU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)mu(?!q)")
_DAMQU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)mqu")
# sa10mu-ds_dst | SA10MU-DS — руководство (RU) → sa10mu-ds after normalize
_SAMU_STEM = re.compile(r"(?i)^sa(?P<nm>\d+)mu(?:-ds(?P<dst>[_-]?dst)?)?$")
_SAMU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)mu")
# Disk export: «SA10MU-DS — руководство (RU).pdf»
_RU_MANUAL_SUFFIX = re.compile(
    r"(?i)\s*[—–\-]\s*руководство(?:\s*\(\s*ru\s*\))?\s*$",
)
_HVD_F_STEM = re.compile(r"(?i)^hvd-(?P<nm>\d+)f-s[_-]?st$")
_HVD_F_CODE = re.compile(r"(?i)^hvd(?:24|230)st?-(?P<nm>\d+)f$")
# hva-5 | hva-5q | hva-5uq | «HVA-5 instruction» (not hva-*p — RF-excluded)
_HVA_STEM = re.compile(r"(?i)^hva-(?P<token>\d+(?:uq|q)?)$")
_HVA_P_STEM = re.compile(r"(?i)^hva-(?P<token>\d+p)$")
_HVA_INSTRUCTION_STEM = re.compile(r"(?i)^hva-5(?:\s+instruction)?$")
_HVA_SKU_BODY = re.compile(
    r"(?i)^hva(?:24|230)s?-(?P<body>\d+(?:uq|q|p)?)$",
)


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


# Prefer translated PDFs when the same basename exists in both folders.
_MANUAL_LANG_SUBDIRS: tuple[str, ...] = ("RU", "EN")


def _manual_search_dirs(manuals_dir: Path) -> list[Path]:
    """Language subfolders (RU → EN) then the manuals root itself."""
    dirs: list[Path] = []
    for name in _MANUAL_LANG_SUBDIRS:
        sub = manuals_dir / name
        if sub.is_dir():
            dirs.append(sub)
    dirs.append(manuals_dir)
    return dirs


def iter_manual_pdfs(manuals_dir: Path, pattern: str = "*.pdf") -> list[Path]:
    """List manuals under ``RU/``, ``EN/``, and the root (deduped, RU first).

    Args:
        manuals_dir: ``_инструкции-pdf`` (or a test tmp dir).
        pattern: Glob relative to each search dir (e.g. ``*.pdf``, ``hvd-*.pdf``).

    Returns:
        Unique file paths by basename (casefold); RU wins over EN/root.
    """
    if not manuals_dir.is_dir():
        return []
    seen_paths: set[Path] = set()
    seen_names: set[str] = set()
    out: list[Path] = []
    for directory in _manual_search_dirs(manuals_dir):
        for path in sorted(directory.glob(pattern)):
            if not path.is_file():
                continue
            key = path.resolve()
            if key in seen_paths:
                continue
            name_key = path.name.casefold()
            if name_key in seen_names:
                continue
            seen_paths.add(key)
            seen_names.add(name_key)
            out.append(path)
    return out


def find_manual_file(manuals_dir: Path, filename: str) -> Path | None:
    """Resolve a basename under ``RU/``, ``EN/``, or the manuals root.

    Args:
        manuals_dir: ``_инструкции-pdf`` root.
        filename: Exact basename (e.g. ``шаровые краны серии 8100.pdf``).

    Returns:
        First existing file (RU preferred), or None.
    """
    if not filename or not manuals_dir.is_dir():
        return None
    name = Path(filename).name
    for directory in _manual_search_dirs(manuals_dir):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def normalize_manual_stem(filename: str) -> str:
    """Strip extension, RU guide suffix, and Disk artefacts from a PDF basename."""
    stem = Path(filename).name
    if stem.casefold().endswith(".pdf"):
        stem = stem[:-4]
    stem = stem.replace("\xa0", "").strip()
    return _RU_MANUAL_SUFFIX.sub("", stem).strip()


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

    for path in iter_manual_pdfs(manuals_dir):
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


def parse_safu_manual_stem(stem: str) -> tuple[int, bool] | None:
    """Parse ``sa5fu-ds_dst`` → ``(5, True)``, ``SA5FU-DS`` → ``(5, False)``."""
    clean = normalize_manual_stem(stem)
    match = _SAFU_STEM.fullmatch(clean)
    if match is None:
        return None
    return int(match.group("nm")), bool(match.group("dst"))


def sku_codes_for_safu_manual(
    torque_nm: int,
    sku_codes: list[str],
    *,
    covers_dst: bool = True,
) -> list[str]:
    """Filter catalog SKU codes that a SAFU DS[/DST] manual covers."""
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        match = _SAFU_CODE.match(compact)
        if match is None or int(match.group("nm")) != torque_nm:
            continue
        if compact.endswith("-dst"):
            if covers_dst:
                out.append(code)
        elif compact.endswith("-ds"):
            out.append(code)
    return out


def discover_safu_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan ``manuals_dir`` for SAFU PDFs and map them to SKU codes.

    When both RU and EN PDFs exist for the same Nm, the first hit wins
    (``iter_manual_pdfs`` yields RU before EN).
    """
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__iregex=r"(?i)^sa[0-9]+fu").values_list(
                "sku_code",
                flat=True,
            ),
        )
    by_nm: dict[int, ManualMatch] = {}
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return [], warnings

    for path in iter_manual_pdfs(manuals_dir):
        parsed = parse_safu_manual_stem(path.name)
        if parsed is None:
            if re.search(r"(?i)sa\d+fu", path.name):
                warnings.append(f"unrecognized SAFU filename: {path.name!r}")
            continue
        torque_nm, covers_dst = parsed
        if torque_nm in by_nm:
            continue
        codes = sku_codes_for_safu_manual(
            torque_nm,
            sku_codes,
            covers_dst=covers_dst,
        )
        if not codes:
            warnings.append(f"no SKU for {path.name!r} (nm={torque_nm} safu)")
            continue
        by_nm[torque_nm] = ManualMatch(
            path=path,
            torque_nm=torque_nm,
            kind="safu_ds_dst" if covers_dst else "safu_ds",
            sku_codes=tuple(codes),
        )
    return list(by_nm.values()), warnings


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


def _parse_nm_list(raw: str) -> tuple[int, ...]:
    """Parse ``8_16_24_32`` → ``(8, 16, 24, 32)``."""
    return tuple(int(part) for part in raw.split("_") if part.isdigit())


def parse_damu_manual_stem(
    stem: str,
) -> tuple[tuple[int, ...], str, int | None] | None:
    """Parse ``da4_6mu-a_as`` / ``da8_16_24_32mu24-d_ds``.

    Returns:
        ``(nm_tuple, kind, voltage_or_None)`` or None.
    """
    clean = normalize_manual_stem(stem)
    match = _DAMU_STEM.fullmatch(clean)
    if match is None:
        return None
    nms = _parse_nm_list(match.group("nms"))
    if not nms:
        return None
    volt_raw = match.group("volt")
    volt = int(volt_raw) if volt_raw else None
    return nms, match.group("kind").casefold(), volt


def parse_damqu_manual_stem(
    stem: str,
) -> tuple[tuple[int, ...], str, int | None] | None:
    """Parse ``da5mqu-a_as`` / ``da8_16_24mqu230-d_ds``."""
    clean = normalize_manual_stem(stem)
    match = _DAMQU_STEM.fullmatch(clean)
    if match is None:
        return None
    nms = _parse_nm_list(match.group("nms"))
    if not nms:
        return None
    volt_raw = match.group("volt")
    volt = int(volt_raw) if volt_raw else None
    return nms, match.group("kind").casefold(), volt


def _sku_matches_control_kind(compact: str, kind: str) -> bool:
    """Return True when SKU suffix matches ``a_as`` or ``d_ds``."""
    if kind == "a_as":
        return compact.endswith("-as") or compact.endswith("-a")
    if kind == "d_ds":
        return compact.endswith("-ds") or compact.endswith("-d")
    return False


def _sku_matches_voltage(compact: str, voltage: int | None) -> bool:
    """Filter by embedded voltage token when the manual is voltage-specific."""
    if voltage is None:
        return True
    return f"{voltage}-" in compact


def sku_codes_for_damu_manual(
    nms: tuple[int, ...],
    kind: str,
    voltage: int | None,
    sku_codes: list[str],
) -> list[str]:
    """Filter DA..MU SKU codes covered by one English manual PDF."""
    wanted = set(nms)
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        match = _DAMU_CODE.match(compact)
        if match is None or int(match.group("nm")) not in wanted:
            continue
        if not _sku_matches_control_kind(compact, kind):
            continue
        if not _sku_matches_voltage(compact, voltage):
            continue
        out.append(code)
    return out


def sku_codes_for_damqu_manual(
    nms: tuple[int, ...],
    kind: str,
    voltage: int | None,
    sku_codes: list[str],
) -> list[str]:
    """Filter DA..MQU SKU codes covered by one English manual PDF."""
    wanted = set(nms)
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        match = _DAMQU_CODE.match(compact)
        if match is None or int(match.group("nm")) not in wanted:
            continue
        if not _sku_matches_control_kind(compact, kind):
            continue
        if not _sku_matches_voltage(compact, voltage):
            continue
        out.append(code)
    return out


def _damu_family_title(nms: tuple[int, ...], kind: str, voltage: int | None) -> str:
    """Human title for a DAMU ProductFile row."""
    nm_label = "/".join(str(n) for n in nms)
    ctrl = "A/AS" if kind == "a_as" else "D/DS"
    if voltage is None:
        return f"Инструкция DA{nm_label}MU ({ctrl})"
    return f"Инструкция DA{nm_label}MU{voltage} ({ctrl})"


def _damqu_family_title(nms: tuple[int, ...], kind: str, voltage: int | None) -> str:
    """Human title for a DAMQU ProductFile row."""
    nm_label = "/".join(str(n) for n in nms)
    ctrl = "A/AS" if kind == "a_as" else "D/DS"
    if voltage is None:
        return f"Инструкция DA{nm_label}MQU ({ctrl})"
    return f"Инструкция DA{nm_label}MQU{voltage} ({ctrl})"


def discover_damu_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan ``manuals_dir`` for DAMU English PDFs and map them to SKU codes."""
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__iregex=r"(?i)^da[0-9]+mu")
            .exclude(sku_code__iregex=r"(?i)^da[0-9]+mqu")
            .values_list("sku_code", flat=True),
        )
    matches: list[ManualMatch] = []
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return matches, warnings

    for path in iter_manual_pdfs(manuals_dir):
        parsed = parse_damu_manual_stem(path.name)
        if parsed is None:
            continue
        nms, kind, volt = parsed
        codes = sku_codes_for_damu_manual(nms, kind, volt, sku_codes)
        if not codes:
            warnings.append(
                f"no SKU for {path.name!r} (nms={nms} kind={kind} volt={volt})",
            )
            continue
        matches.append(
            ManualMatch(
                path=path,
                torque_nm=nms[0],
                kind=f"damu_{kind}" + (f"_{volt}" if volt else ""),
                sku_codes=tuple(codes),
            ),
        )
    return matches, warnings


def discover_damqu_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan ``manuals_dir`` for DAMQU English PDFs and map them to SKU codes."""
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__iregex=r"(?i)^da[0-9]+mqu").values_list(
                "sku_code",
                flat=True,
            ),
        )
    matches: list[ManualMatch] = []
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return matches, warnings

    for path in iter_manual_pdfs(manuals_dir):
        parsed = parse_damqu_manual_stem(path.name)
        if parsed is None:
            continue
        nms, kind, volt = parsed
        codes = sku_codes_for_damqu_manual(nms, kind, volt, sku_codes)
        if not codes:
            warnings.append(
                f"no SKU for {path.name!r} (mqu nms={nms} kind={kind} volt={volt})",
            )
            continue
        matches.append(
            ManualMatch(
                path=path,
                torque_nm=nms[0],
                kind=f"damqu_{kind}" + (f"_{volt}" if volt else ""),
                sku_codes=tuple(codes),
            ),
        )
    return matches, warnings


def _attach_matches(
    matches: list[ManualMatch],
    warnings: list[str],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Shared ProductFile upsert for DAMU/DAMQU manual matches."""
    summary: dict[str, Any] = {
        "manuals": len(matches),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "warnings": list(warnings),
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
            parsed_damu = parse_damu_manual_stem(match.path.name)
            parsed_damqu = parse_damqu_manual_stem(match.path.name)
            if parsed_damu is not None:
                nms, kind, volt = parsed_damu
                title = _damu_family_title(nms, kind, volt)
            elif parsed_damqu is not None:
                nms, kind, volt = parsed_damqu
                title = _damqu_family_title(nms, kind, volt)
            else:
                title = f"Инструкция ({match.kind})"
            # Fallback attach keeps 230 title semantics but labels 24 V SKUs clearly.
            if match.kind.endswith("_fallback"):
                title = "Инструкция DA8/16/24MQU (D/DS)"
            basename = _storage_basename(match.path)
            for code in match.sku_codes:
                sku = code_to_sku.get(code.casefold())
                if sku is None:
                    summary["warnings"].append(f"SKU missing in DB: {code}")
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
    return summary


def attach_damu_manuals(
    manuals_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update ProductFile datasheets for DAMU SKUs from English PDFs."""
    matches, warnings = discover_damu_manuals(manuals_dir)
    return _attach_matches(matches, warnings, dry_run=dry_run)


def attach_damqu_manuals(
    manuals_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update ProductFile datasheets for DAMQU SKUs from English PDFs."""
    matches, warnings = discover_damqu_manuals(manuals_dir)

    # No da8_16_24mqu24-d_ds.pdf — reuse 230 V D/DS for catalog DA8MQU24-D/DS.
    covered = {c.casefold() for m in matches for c in m.sku_codes}
    sku_codes = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^da[0-9]+mqu").values_list(
            "sku_code",
            flat=True,
        ),
    )
    missing_24_d = [
        c for c in sku_codes_for_damqu_manual((8, 16, 24), "d_ds", 24, sku_codes) if c.casefold() not in covered
    ]
    fallback = find_manual_file(manuals_dir, "da8_16_24mqu230-d_ds.pdf")
    if missing_24_d and fallback is not None and fallback.is_file():
        matches.append(
            ManualMatch(
                path=fallback,
                torque_nm=8,
                kind="damqu_d_ds_24_fallback",
                sku_codes=tuple(missing_24_d),
            ),
        )
        warnings.append(
            f"DAMQU24 D/DS: fallback PDF {fallback.name} → {missing_24_d}",
        )

    return _attach_matches(matches, warnings, dry_run=dry_run)


_DAMQU_EDITION_TAIL = re.compile(
    r"(?i)^da(?P<nm>\d+)mqu(?P<tail>(?:24|230)-(?:as|ds|a|d))$",
)


def _damqu_edition_tail(sku_code: str) -> tuple[int, str] | None:
    """Return (nm, ``24-A``-style tail) for DA..MQU, else None."""
    match = _DAMQU_EDITION_TAIL.fullmatch((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm")), match.group("tail").upper()


def _clone_one_manual(
    *,
    donor_file: ProductFile,
    target: SKU,
    dry_run: bool,
) -> str:
    """Upsert one datasheet onto ``target`` from ``donor_file`` bytes."""
    title = (donor_file.title or "").strip()
    if not title:
        return "skipped"
    existing = ProductFile.objects.filter(sku=target, title=title).first()
    if dry_run:
        return "update" if existing is not None else "create"

    payload = b""
    if donor_file.file:
        donor_file.file.open("rb")
        try:
            payload = donor_file.file.read()
        finally:
            donor_file.file.close()
    if not payload:
        return "skipped"
    basename = Path(getattr(donor_file.file, "name", "") or "manual.pdf").name
    with transaction.atomic():
        if existing is None:
            pf = ProductFile(
                sku=target,
                title=title[:300],
                file_type=donor_file.file_type or ProductFile.FileType.DATASHEET,
                is_published=donor_file.is_published,
                sort_order=donor_file.sort_order,
            )
            pf.file.save(basename, ContentFile(payload), save=True)
            return "create"
        current_size = existing.file.size if existing.file else 0
        if current_size != len(payload):
            existing.file.save(basename, ContentFile(payload), save=True)
            existing.file_type = donor_file.file_type or existing.file_type
            existing.is_published = donor_file.is_published
            existing.sort_order = donor_file.sort_order
            existing.save(
                update_fields=["file_type", "is_published", "sort_order", "updated_at"],
            )
            return "update"
        return "skipped"


def clone_damqu_manuals_from_donor(
    *,
    donor_nm: int = 8,
    target_nms: tuple[int, ...] = (16, 24),
    dry_run: bool = False,
) -> dict[str, Any]:
    """Copy ProductFile manuals from DA{donor}MQU onto DA16/DA24 same editions.

    EN family PDFs (``da8_16_24mqu*``) already cover 8/16/24; when the manuals
    dir is missing on the host, clone from DA8 rows that were attached earlier.

    Returns:
        Counters: created, updated, skipped, targets, dry_run.
    """
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "targets": 0,
        "dry_run": dry_run,
        "donor_nm": donor_nm,
        "target_nms": list(target_nms),
    }
    donors = {
        sku.sku_code.upper(): sku
        for sku in SKU.objects.filter(sku_code__iregex=rf"(?i)^da{donor_nm}mqu").prefetch_related(
            "files",
        )
    }
    targets = SKU.objects.filter(
        sku_code__iregex=rf"(?i)^da({'|'.join(str(n) for n in target_nms)})mqu",
        is_published=True,
    ).order_by("sku_code")
    for target in targets:
        parsed = _damqu_edition_tail(target.sku_code or "")
        if parsed is None:
            summary["skipped"] += 1
            continue
        _, tail = parsed
        donor = donors.get(f"DA{donor_nm}MQU{tail}")
        if donor is None:
            summary["skipped"] += 1
            continue
        summary["targets"] += 1
        for pf in donor.files.all():
            action = _clone_one_manual(donor_file=pf, target=target, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
            elif action == "update":
                summary["updated"] += 1
            else:
                summary["skipped"] += 1
    return summary


def parse_samu_manual_stem(stem: str) -> tuple[int, bool] | None:
    """Parse ``sa10mu-ds_dst`` → ``(10, True)``, ``SA10MU-DS`` → ``(10, False)``."""
    clean = normalize_manual_stem(stem)
    match = _SAMU_STEM.fullmatch(clean)
    if match is None:
        return None
    return int(match.group("nm")), bool(match.group("dst"))


def sku_codes_for_samu_manual(
    torque_nm: int,
    sku_codes: list[str],
    *,
    covers_dst: bool = True,
) -> list[str]:
    """Filter SA..MU DS[/DST] SKU codes for one manual."""
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        match = _SAMU_CODE.match(compact)
        if match is None or int(match.group("nm")) != torque_nm:
            continue
        if compact.endswith("-dst"):
            if covers_dst:
                out.append(code)
        elif compact.endswith("-ds"):
            out.append(code)
    return out


def discover_samu_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan ``manuals_dir`` for SAMU PDFs (RU preferred over EN)."""
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__iregex=r"(?i)^sa[0-9]+mu").values_list(
                "sku_code",
                flat=True,
            ),
        )
    by_nm: dict[int, ManualMatch] = {}
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return [], warnings
    for path in iter_manual_pdfs(manuals_dir):
        parsed = parse_samu_manual_stem(path.name)
        if parsed is None:
            if re.search(r"(?i)sa\d+mu", path.name):
                warnings.append(f"unrecognized SAMU filename: {path.name!r}")
            continue
        torque_nm, covers_dst = parsed
        if torque_nm in by_nm:
            continue
        codes = sku_codes_for_samu_manual(
            torque_nm,
            sku_codes,
            covers_dst=covers_dst,
        )
        if not codes:
            warnings.append(f"no SKU for {path.name!r} (nm={torque_nm} samu)")
            continue
        by_nm[torque_nm] = ManualMatch(
            path=path,
            torque_nm=torque_nm,
            kind="samu_ds_dst" if covers_dst else "samu_ds",
            sku_codes=tuple(codes),
        )
    return list(by_nm.values()), warnings


def _samu_manual_title(torque_nm: int) -> str:
    """Public ProductFile title for SA..MU (DS only; DST cards unpublished)."""
    return f"Инструкция SA{torque_nm}MU (DS)"


def _samu_manual_legacy_title(torque_nm: int) -> str:
    """Pre-RU title that still mentioned DST — renamed on attach."""
    return f"Инструкция SA{torque_nm}MU (DS/DST)"


def _find_samu_instruction_file(sku: SKU, torque_nm: int) -> ProductFile | None:
    """Prefer current title; fall back to legacy ``(DS/DST)`` row."""
    title = _samu_manual_title(torque_nm)
    existing = ProductFile.objects.filter(sku=sku, title=title).first()
    if existing is not None:
        return existing
    return ProductFile.objects.filter(
        sku=sku,
        title=_samu_manual_legacy_title(torque_nm),
    ).first()


def rename_legacy_samu_manual_titles(*, dry_run: bool = False) -> int:
    """Rename leftover ``Инструкция SA{n}MU (DS/DST)`` → ``… (DS)``."""
    legacy = list(
        ProductFile.objects.filter(title__regex=r"^Инструкция SA\d+MU \(DS/DST\)$"),
    )
    if dry_run or not legacy:
        return len(legacy)
    for pf in legacy:
        pf.title = pf.title.replace(" (DS/DST)", " (DS)", 1)
        pf.save(update_fields=["title"])
    return len(legacy)


def attach_samu_manuals(
    manuals_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update ProductFile datasheets for SAMU SKUs."""
    matches, warnings = discover_samu_manuals(manuals_dir)
    summary: dict[str, Any] = {
        "manuals": len(matches),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "renamed_titles": 0,
        "warnings": warnings,
        "dry_run": dry_run,
        "by_sku": {},
    }
    if not matches:
        summary["renamed_titles"] = rename_legacy_samu_manual_titles(dry_run=dry_run)
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
            title = _samu_manual_title(match.torque_nm)
            basename = _storage_basename(match.path)
            for code in match.sku_codes:
                sku = code_to_sku.get(code.casefold())
                if sku is None:
                    warnings.append(f"SKU missing in DB: {code}")
                    continue
                existing = _find_samu_instruction_file(sku, match.torque_nm)
                if dry_run:
                    summary["by_sku"].setdefault(code, []).append(title)
                    summary["created" if existing is None else "updated"] += 1
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
                else:
                    changed = False
                    if existing.title != title:
                        existing.title = title
                        existing.save(update_fields=["title"])
                        changed = True
                    current_size = existing.file.size if existing.file else 0
                    if current_size != len(payload):
                        existing.file.save(basename, ContentFile(payload), save=True)
                        changed = True
                    summary["updated" if changed else "skipped"] += 1
                summary["by_sku"].setdefault(code, []).append(title)
        if dry_run:
            transaction.set_rollback(True)
    summary["renamed_titles"] = rename_legacy_samu_manual_titles(dry_run=dry_run)
    summary["warnings"] = warnings
    return summary


def parse_hvd_f_manual_stem(stem: str) -> int | None:
    """Parse ``hvd-5f-s_st`` → ``5``."""
    clean = normalize_manual_stem(stem)
    match = _HVD_F_STEM.fullmatch(clean)
    if match is None:
        return None
    return int(match.group("nm"))


def sku_codes_for_hvd_f_manual(torque_nm: int, sku_codes: list[str]) -> list[str]:
    """Map HVD *F manuals onto catalog ``HVD*S-{nm}F`` / ``HVD*ST-{nm}F`` only."""
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        match = _HVD_F_CODE.fullmatch(compact)
        if match is None:
            continue
        if int(match.group("nm")) == torque_nm:
            out.append(code)
    return out


def discover_hvd_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan for HVD *F English PDFs and map to HVD-…F catalog SKUs."""
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__iregex=r"(?i)^hvd(24|230)st?-\d+f$").values_list(
                "sku_code",
                flat=True,
            ),
        )
    matches: list[ManualMatch] = []
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return matches, warnings
    for path in iter_manual_pdfs(manuals_dir, "hvd-*.pdf"):
        torque_nm = parse_hvd_f_manual_stem(path.name)
        if torque_nm is None:
            warnings.append(f"unrecognized HVD filename: {path.name!r}")
            continue
        codes = sku_codes_for_hvd_f_manual(torque_nm, sku_codes)
        if not codes:
            warnings.append(
                f"no catalog SKU for {path.name!r} (expected HVD*S-{torque_nm}F / HVD*ST-{torque_nm}F)",
            )
            continue
        matches.append(
            ManualMatch(
                path=path,
                torque_nm=torque_nm,
                kind="hvd_f_s_st",
                sku_codes=tuple(codes),
            ),
        )
    return matches, warnings


def attach_hvd_manuals(
    manuals_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update ProductFile datasheets for matching HVD SKUs."""
    matches, warnings = discover_hvd_manuals(manuals_dir)
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
            title = f"Инструкция HVD-{match.torque_nm}F (S/ST)"
            basename = _storage_basename(match.path)
            for code in match.sku_codes:
                sku = code_to_sku.get(code.casefold())
                if sku is None:
                    warnings.append(f"SKU missing in DB: {code}")
                    continue
                existing = ProductFile.objects.filter(sku=sku, title=title).first()
                if dry_run:
                    summary["by_sku"].setdefault(code, []).append(title)
                    summary["created" if existing is None else "updated"] += 1
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


def parse_hva_manual_token(stem: str) -> str | None:
    """Parse ``hva-5q`` / ``HVA-5 instruction`` → family token ``5`` / ``5q``.

    Spring ``hva-*p`` manuals are RF-excluded (Chinese market) — return None.
    """
    clean = normalize_manual_stem(stem)
    if _HVA_P_STEM.fullmatch(clean):
        return None
    if _HVA_INSTRUCTION_STEM.fullmatch(clean):
        return "5"
    match = _HVA_STEM.fullmatch(clean)
    if match is None:
        return None
    return match.group("token").casefold()


def sku_codes_for_hva_manual(token: str, sku_codes: list[str]) -> list[str]:
    """Map PDF token onto catalog ``HVA(24|230)[S]-{token}`` codes only."""
    want = token.casefold()
    out: list[str] = []
    for code in sku_codes:
        compact = code.strip().casefold().replace(" ", "")
        match = _HVA_SKU_BODY.fullmatch(compact)
        if match is None:
            continue
        if match.group("body").casefold() == want:
            out.append(code)
    return out


def discover_hva_manuals(
    manuals_dir: Path,
    *,
    sku_codes: list[str] | None = None,
) -> tuple[list[ManualMatch], list[str]]:
    """Scan for ``hva-*.pdf`` / legacy HVA-5 instruction and map to HVA SKUs."""
    if sku_codes is None:
        sku_codes = list(
            SKU.objects.filter(sku_code__istartswith="HVA").values_list("sku_code", flat=True),
        )
    matches: list[ManualMatch] = []
    warnings: list[str] = []
    if not manuals_dir.is_dir():
        warnings.append(f"manuals dir missing: {manuals_dir}")
        return matches, warnings

    paths = sorted(
        {
            *iter_manual_pdfs(manuals_dir, "hva-*.pdf"),
            *iter_manual_pdfs(manuals_dir, "HVA-*.pdf"),
            *iter_manual_pdfs(manuals_dir, "HVA-5 instruction.pdf"),
        },
        key=lambda p: (
            # Prefer ascii ``hva-5.pdf`` over legacy ``HVA-5 instruction.pdf``.
            0 if _HVA_STEM.fullmatch(normalize_manual_stem(p.name)) else 1,
            p.name.casefold(),
        ),
    )
    # Prefer ``hva-5.pdf`` over legacy ``HVA-5 instruction.pdf`` for token 5.
    seen_tokens: set[str] = set()
    for path in paths:
        token = parse_hva_manual_token(path.name)
        if token is None:
            if _HVA_P_STEM.fullmatch(normalize_manual_stem(path.name)):
                warnings.append(
                    f"skip RF-excluded HVA-P manual: {path.name!r}",
                )
            elif path.name.casefold().startswith("hva"):
                warnings.append(f"unrecognized HVA filename: {path.name!r}")
            continue
        if token in seen_tokens:
            warnings.append(f"duplicate HVA manual for {token!r}, skip {path.name!r}")
            continue
        codes = sku_codes_for_hva_manual(token, sku_codes)
        if not codes:
            warnings.append(
                f"no catalog SKU for {path.name!r} (expected HVA*S?-{token.upper()})",
            )
            continue
        seen_tokens.add(token)
        nm_match = re.match(r"^(\d+)", token)
        torque_nm = int(nm_match.group(1)) if nm_match else 0
        matches.append(
            ManualMatch(
                path=path,
                torque_nm=torque_nm,
                kind=token,
                sku_codes=tuple(codes),
            ),
        )
    return matches, warnings


def attach_hva_manuals(
    manuals_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create/update ProductFile datasheets for matching HVA SKUs."""
    matches, warnings = discover_hva_manuals(manuals_dir)
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
            label = match.kind.upper()
            title = f"Инструкция HVA-{label}"
            basename = _storage_basename(match.path)
            for code in match.sku_codes:
                sku = code_to_sku.get(code.casefold())
                if sku is None:
                    warnings.append(f"SKU missing in DB: {code}")
                    continue
                existing = ProductFile.objects.filter(sku=sku, title=title).first()
                if dry_run:
                    summary["by_sku"].setdefault(code, []).append(title)
                    summary["created" if existing is None else "updated"] += 1
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
