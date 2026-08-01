"""Extra media-webp tiles: montage, emergency feedback wiring, SAF72.

Source (Yandex Disk ``media-webp/``)::

    montazhnaya_sxema_{hv|da2mu|da4:6mu|…}.webp
    podkluchenie_avariynaya_obratnaya_sviaz.webp
    podkluchenie_avariynaya_obratnaya_sviaz_3-spdt.webp
    termodatchik_saf72.webp
    sxema_termodatchik_saf72.webp

Gallery order (with existing manual wiring/dims)::

    0 product hero (−ds body also on −dst)
    1 SAF72 photo (−dst only)
    2 SAF72 schema (−dst only)
    4 montage
    5 manual wiring
    7 emergency-feedback wiring (**HV *QA only**)
    8 dimensions
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q

from catalog.etl.hv_media_webp import default_media_webp_root
from catalog.etl.sku_variant import sku_code_is_thermal
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

_SOURCE = "https://hoocon.ru/.local-assets/media-webp/{stem}.webp"

SORT_SAF72_PHOTO: Final[int] = 1
SORT_SAF72_SCHEMA: Final[int] = 2
SORT_MONTAGE: Final[int] = 4
# After manual wiring(5) / legacy dims(6); before SORT_DIMENSIONS=8 when present.
SORT_EMERGENCY: Final[int] = 7

_SAF72_PHOTO_STEM = "termodatchik_saf72"
_SAF72_SCHEMA_STEM = "sxema_termodatchik_saf72"
_EMERGENCY_STEM = "podkluchenie_avariynaya_obratnaya_sviaz"
_EMERGENCY_3_STEM = "podkluchenie_avariynaya_obratnaya_sviaz_3-spdt"
# Album / pack: аварийная обратная связь only on HVD/HVA *QA (not plain -S aux).
_QA_SKU_RE = re.compile(r"(?i)^hv[ad].*qa$")

_MONTAGE_RE = re.compile(
    r"(?i)^montazhnaya_sxema_(?:"
    r"(?P<hv>hv)|"
    r"(?P<fam>da|sa)(?P<nms>\d+(?::\d+)*)(?P<series>fu|mu|mqu|eu)"
    r")$",
)

# When a family has no own montage, reuse a neighbour (same idea as PDF fallbacks).
_MONTAGE_SERIES_FALLBACK: Final[dict[tuple[str, str], str]] = {
    ("da", "mqu"): "mu",
    ("da", "eu"): "mu",
}
_MONTAGE_NM_FALLBACK: Final[dict[tuple[str, str], dict[int, int]]] = {
    ("sa", "fu"): {3: 5},
    ("da", "fu"): {3: 5},
    ("sa", "mu"): {7: 10, 15: 10},
    ("da", "mu"): {32: 24},
    # After series→mu: DA5MQU≈DA4/6; DA8/16/24MQU≈da8:16:24mu montage (10/20 legacy→8/24).
    ("da", "mqu"): {5: 6, 10: 8, 20: 24},
}


@dataclass(frozen=True, slots=True)
class _MontageShot:
    """One montage diagram pack file."""

    stem: str
    path: Path
    kind: str  # hv | da_sa
    family: str | None
    nms: frozenset[int]
    series: str | None


def _webp(
    path: Path,
    cache: dict[str, bytes],
    *,
    dry_run: bool,
    trim_alpha: bool = False,
    flatten_white: bool = False,
) -> bytes:
    """Read+re-encode once per path/options (trim+white for paper diagrams)."""
    key = f"{path.resolve()}|trim={int(trim_alpha)}|white={int(flatten_white)}"
    if key not in cache:
        if dry_run:
            cache[key] = b""
        else:
            cache[key] = convert_bytes_to_webp(
                path.read_bytes(),
                quality=DEFAULT_WEBP_QUALITY,
                max_edge=MAX_EDGE_PX,
                trim_alpha=trim_alpha,
                flatten_white=flatten_white,
            )
    return cache[key]


def _upsert_tile(
    sku: SKU,
    *,
    stem: str,
    webp: bytes,
    alt: str,
    sort_order: int,
    dry_run: bool,
) -> str:
    """Create/update a non-hero gallery tile by stable source_url."""
    source_url = _SOURCE.format(stem=stem)
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return "update" if existing else "create"

    filename = f"{sku.sku_code.lower()}-{stem}.webp"
    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=alt[:300],
                source_url=source_url,
                sort_order=sort_order,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            return "create"
        existing.alt = alt[:300]
        existing.sort_order = sort_order
        existing.is_published = True
        existing.image.save(filename, ContentFile(webp), save=False)
        existing.full_clean()
        existing.save()
        return "update"


def _demote_tilda_montage(sku: SKU, *, dry_run: bool) -> int:
    """Unpublish Tilda montage tiles once a local montage exists.

    Tilda alts vary: ``Монтажная схема …`` or ``схема монтажная …``.
    """
    qs = ProductImage.objects.filter(
        sku=sku,
        is_published=True,
        source_url__icontains="tildacdn",
    ).filter(
        Q(alt__icontains="монтажная схема") | Q(alt__icontains="схема монтажная"),
    )
    count = qs.count()
    if count and not dry_run:
        qs.update(is_published=False)
    return count


def demote_tilda_montages_where_local_exists(*, dry_run: bool = False) -> int:
    """Demote Tilda montage rows on SKUs that already have media-webp montage."""
    sku_ids = (
        ProductImage.objects.filter(
            is_published=True,
            source_url__icontains="montazhnaya_sxema",
        )
        .values_list("sku_id", flat=True)
        .distinct()
    )
    total = 0
    for sku in SKU.objects.filter(pk__in=sku_ids).order_by("sku_code"):
        total += _demote_tilda_montage(sku, dry_run=dry_run)
    return total


def sku_code_is_hv_qa(sku_code: str | None) -> bool:
    """True for HVA/HVD emergency-feedback editions (``…QA``)."""
    return bool(_QA_SKU_RE.fullmatch((sku_code or "").strip()))


def _demote_emergency_on_non_qa(*, dry_run: bool) -> int:
    """Unpublish аварийная-связь tiles mistakenly attached to non-QA SKUs."""
    qs = ProductImage.objects.filter(
        is_published=True,
        source_url__icontains="avariynaya_obratnaya",
    ).exclude(sku__sku_code__iregex=r"(?i)^hv[ad].*qa$")
    count = qs.count()
    if count and not dry_run:
        qs.update(is_published=False)
    return count


def _parse_montage_stem(stem: str, path: Path) -> _MontageShot | None:
    """Parse ``montazhnaya_sxema_da4:6mu`` / ``montazhnaya_sxema_hv``."""
    match = _MONTAGE_RE.fullmatch((stem or "").strip())
    if match is None:
        return None
    if match.group("hv"):
        return _MontageShot(
            stem=stem,
            path=path,
            kind="hv",
            family=None,
            nms=frozenset(),
            series=None,
        )
    nms = frozenset(int(part) for part in match.group("nms").split(":"))
    return _MontageShot(
        stem=stem,
        path=path,
        kind="da_sa",
        family=match.group("fam").casefold(),
        nms=nms,
        series=match.group("series").casefold(),
    )


def _scan_montages(root: Path) -> list[_MontageShot]:
    """Index montage diagrams in the pack."""
    shots: list[_MontageShot] = []
    for path in sorted(root.glob("montazhnaya_sxema_*.webp")):
        parsed = _parse_montage_stem(path.stem, path)
        if parsed is not None:
            shots.append(parsed)
    return shots


def _pick_montage(sku_code: str, shots: list[_MontageShot]) -> _MontageShot | None:
    """Match HV or DA/SA montage; apply Nm / series neighbour fallbacks."""
    code = (sku_code or "").strip().casefold().replace(" ", "")
    if re.match(r"hv[ad]", code):
        for shot in shots:
            if shot.kind == "hv":
                return shot
        return None

    match = re.match(r"(?i)^(da|sa)(\d+)(fu|mu|mqu|eu)", code)
    if match is None:
        return None
    fam = match.group(1).casefold()
    nm_raw = int(match.group(2))
    series = match.group(3).casefold()

    series_candidates = [series]
    series_fb = _MONTAGE_SERIES_FALLBACK.get((fam, series))
    if series_fb and series_fb not in series_candidates:
        series_candidates.append(series_fb)

    best: _MontageShot | None = None
    best_specificity = -1
    for try_series in series_candidates:
        nm = _MONTAGE_NM_FALLBACK.get((fam, series), {}).get(nm_raw, nm_raw)
        if try_series != series:
            nm = _MONTAGE_NM_FALLBACK.get((fam, try_series), {}).get(nm, nm)
        for shot in shots:
            if shot.kind != "da_sa":
                continue
            if shot.family != fam or shot.series != try_series:
                continue
            if nm not in shot.nms:
                continue
            # Prefer exact series, then tighter Nm sets.
            specificity = (100 if try_series == series else 50) - len(shot.nms)
            if specificity > best_specificity:
                best_specificity = specificity
                best = shot
    return best


def apply_media_webp_extras(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
) -> dict[str, Any]:
    """Attach montage / emergency wiring / SAF72 tiles from media-webp.

    Args:
        dry_run: Count only.
        photo_root: Override pack directory.

    Returns:
        Counters by tile kind + demoted Tilda montage.
    """
    root = photo_root or default_media_webp_root()
    summary: dict[str, Any] = {
        "montage": 0,
        "emergency": 0,
        "saf72_photo": 0,
        "saf72_schema": 0,
        "demoted_tilda_montage": 0,
        "demoted_emergency_non_qa": 0,
        "dry_run": dry_run,
        "photo_root": str(root) if root else "",
        "missing": [],
    }
    if root is None or not root.is_dir():
        summary["missing"].append("(root not found)")
        return summary

    cache: dict[str, bytes] = {}
    montages = _scan_montages(root)

    paths = {
        "saf72_photo": root / f"{_SAF72_PHOTO_STEM}.webp",
        "saf72_schema": root / f"{_SAF72_SCHEMA_STEM}.webp",
        "emergency": root / f"{_EMERGENCY_STEM}.webp",
        "emergency_3": root / f"{_EMERGENCY_3_STEM}.webp",
    }
    for key, path in paths.items():
        if not path.is_file():
            summary["missing"].append(path.name)

    skus = list(
        SKU.objects.filter(is_published=True)
        .filter(sku_code__iregex=r"(?i)^(?:da|sa)\d|^hv[ad]")
        .order_by("sku_code"),
    )

    for sku in skus:
        code = sku.sku_code or ""
        montage = _pick_montage(code, montages)
        if montage is not None:
            action = _upsert_tile(
                sku,
                stem=montage.stem,
                webp=_webp(
                    montage.path,
                    cache,
                    dry_run=dry_run,
                    trim_alpha=True,
                    flatten_white=True,
                ),
                alt=f"{code} | Монтажная схема",
                sort_order=SORT_MONTAGE,
                dry_run=dry_run,
            )
            if action:
                summary["montage"] += 1
            summary["demoted_tilda_montage"] += _demote_tilda_montage(sku, dry_run=dry_run)

        has_emergency = paths["emergency"].is_file() or paths["emergency_3"].is_file()
        if sku_code_is_hv_qa(code) and has_emergency:
            # QA packs use the 3-SPDT emergency-feedback diagram when present.
            stem = _EMERGENCY_3_STEM if paths["emergency_3"].is_file() else _EMERGENCY_STEM
            path = paths["emergency_3"] if stem == _EMERGENCY_3_STEM else paths["emergency"]
            _upsert_tile(
                sku,
                stem=stem,
                webp=_webp(
                    path,
                    cache,
                    dry_run=dry_run,
                    trim_alpha=True,
                    flatten_white=True,
                ),
                alt=f"{code} | Схема подключения с аварийной обратной связью",
                sort_order=SORT_EMERGENCY,
                dry_run=dry_run,
            )
            summary["emergency"] += 1

        if sku_code_is_thermal(code):
            if paths["saf72_photo"].is_file():
                _upsert_tile(
                    sku,
                    stem=_SAF72_PHOTO_STEM,
                    webp=_webp(paths["saf72_photo"], cache, dry_run=dry_run),
                    alt=f"{code} | Термодатчик SAF72",
                    sort_order=SORT_SAF72_PHOTO,
                    dry_run=dry_run,
                )
                summary["saf72_photo"] += 1
            if paths["saf72_schema"].is_file():
                _upsert_tile(
                    sku,
                    stem=_SAF72_SCHEMA_STEM,
                    webp=_webp(
                        paths["saf72_schema"],
                        cache,
                        dry_run=dry_run,
                        trim_alpha=True,
                        flatten_white=True,
                    ),
                    alt=f"{code} | Схема термодатчика SAF72",
                    sort_order=SORT_SAF72_SCHEMA,
                    dry_run=dry_run,
                )
                summary["saf72_schema"] += 1

    summary["demoted_emergency_non_qa"] = _demote_emergency_on_non_qa(dry_run=dry_run)
    return summary
