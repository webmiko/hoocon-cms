"""Attach optimized DA/SA product heroes from the flat ``media-webp`` pack.

Source (Yandex Disk)::

    ~/Yandex.Disk.localized/фото для сайта/media-webp/
        da3fu-d:ds.webp, da5fu24-a:as.webp, da10:15:20fu-a:as.webp,
        da10:15:20fu-d:ds.webp, …
        sa3fu-ds.webp, sa3fu-dst.webp, sa10:15mu-ds.webp, …

Edition rules
-------------
- Pack stem ``…-d:ds`` / ``…-a:as`` covers both suffixes.
- SA ``…-ds`` is the **body** hero for both DS and DST cards.
- Dedicated ``…-dst`` body shots are **not** preferred: DST cards use the
  ``-ds`` photo plus SAF72 tiles from ``media_webp_extras`` (full DST set).
- If only a ``-dst`` pack exists (no ``-ds``), it is still used as fallback.
- DA10/15/20 FU ``-A`` / ``-AS`` use the shared ``…-d:ds`` body photo (same
  chassis as on/off); ``da10:15:20fu-a:as.webp`` is not attached as hero.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import transaction

from catalog.etl.hv_media_webp import (
    SORT_PRODUCT,
    _demote_other_product_shots,
    default_media_webp_root,
)
from catalog.etl.image_upsert import upsert_sku_image
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

_SOURCE_URL = "https://hoocon.ru/.local-assets/media-webp/{stem}-product.webp"
_CLONE_SOURCE_URL = "https://hoocon.ru/.local-assets/media-webp/clone/{stem}"

_STEM_RE = re.compile(
    r"(?i)^"
    r"(?P<fam>da|sa)"
    r"(?P<nms>\d+(?::\d+)*)"
    r"(?P<series>fu|mu|mqu|eu)"
    r"(?P<volt>24|230)?"
    r"-(?P<eds>.+)$",
)
_SKU_RE = re.compile(
    r"(?i)^"
    r"(?P<fam>da|sa)"
    r"(?P<nm>\d+)"
    r"(?P<series>fu|mu|mqu|eu)"
    r"(?P<volt>24|230)?"
    r"-(?P<ed>as|dst|ds|a|d)$",
)

# Pack masks without this Nm → reuse neighbour (DA32 ≈ DA24).
# DA8/16/24 MQU heroes come from the RU manual cutout, not ``da10:20mqu``.
_PHOTO_NM_FALLBACK: dict[tuple[str, str], dict[int, int]] = {
    ("da", "mu"): {32: 24},
}
_DAMQU_FAMILY_NM: frozenset[int] = frozenset({8, 16, 24})
_DAMQU_MANUAL_SOURCE = "https://hoocon.ru/.local-assets/manuals-ru/{folder}-{kind}.webp"
_DAMQU_ALT_MODEL = re.compile(r"^(DA\d+MQU[0-9A-Z-]*)(?P<rest>.*)$", re.IGNORECASE)

_DAMQU_EDITION_RE = re.compile(
    r"(?i)^da(?P<nm>\d+)mqu(?P<tail>(?:24|230)-(?:as|ds|a|d))$",
)

# DA10/15/20 FU modulating editions share the on/off body photo.
_DAFU_MOD_USES_ON_OFF_BODY_NM: frozenset[int] = frozenset({10, 15, 20})


@dataclass(frozen=True, slots=True)
class _PackShot:
    """One media-webp cutout for DA/SA editions."""

    stem: str
    path: Path
    family: str
    nms: frozenset[int]
    series: str
    voltage: str | None
    editions: frozenset[str]


@dataclass(frozen=True, slots=True)
class _SkuParts:
    """Parsed DA/SA edition code."""

    family: str
    nm: int
    series: str
    voltage: str | None
    edition: str
    code: str


def _parse_stem(stem: str, path: Path) -> _PackShot | None:
    """Parse ``da10:15:20fu-d:ds`` / ``sa3fu-dst`` pack stem."""
    match = _STEM_RE.fullmatch((stem or "").strip())
    if match is None:
        return None
    nms = frozenset(int(part) for part in match.group("nms").split(":"))
    eds = frozenset(part.strip().casefold() for part in match.group("eds").split(":") if part.strip())
    if not eds:
        return None
    volt = match.group("volt")
    return _PackShot(
        stem=stem,
        path=path,
        family=match.group("fam").casefold(),
        nms=nms,
        series=match.group("series").casefold(),
        voltage=volt.casefold() if volt else None,
        editions=eds,
    )


def _parse_sku(sku_code: str) -> _SkuParts | None:
    """Parse ``da5fu24-ds`` / ``SA10MU230-DST``."""
    match = _SKU_RE.fullmatch((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    volt = match.group("volt")
    return _SkuParts(
        family=match.group("fam").casefold(),
        nm=int(match.group("nm")),
        series=match.group("series").casefold(),
        voltage=volt.casefold() if volt else None,
        edition=match.group("ed").casefold(),
        code=(sku_code or "").strip(),
    )


def _edition_score(shot: _PackShot, edition: str) -> int:
    """Higher is better. DST prefers pure ``-ds`` body over ``-dst`` composite."""
    eds = shot.editions
    if edition == "dst":
        # Prefer DS-only pack (SAF72 attached separately on DST cards).
        if "ds" in eds and "dst" not in eds:
            return 3
        if "dst" in eds and "ds" not in eds:
            return 1
        if "ds" in eds:
            return 2
        return 0
    if edition in eds:
        return 2
    return 0


def _photo_edition_for_sku(parts: _SkuParts) -> str:
    """Pack edition key to match for this SKU's body hero.

    DA10/15/20 FU ``-A``/``-AS`` reuse the on/off ``-D``/``-DS`` chassis photo.
    """
    if (
        parts.family == "da"
        and parts.series == "fu"
        and parts.nm in _DAFU_MOD_USES_ON_OFF_BODY_NM
        and parts.edition in {"a", "as"}
    ):
        return "ds"
    return parts.edition


def _pick_shot(parts: _SkuParts, shots: list[_PackShot]) -> _PackShot | None:
    """Best pack file for this SKU (voltage + edition, DST prefers DS body)."""
    fallback = _PHOTO_NM_FALLBACK.get((parts.family, parts.series), {})
    nm = fallback.get(parts.nm, parts.nm)
    photo_edition = _photo_edition_for_sku(parts)
    best: _PackShot | None = None
    best_key: tuple[int, int] = (0, 0)
    for shot in shots:
        if shot.family != parts.family:
            continue
        if nm not in shot.nms:
            continue
        if shot.series != parts.series:
            continue
        if shot.voltage is not None and parts.voltage is not None and shot.voltage != parts.voltage:
            continue
        if shot.voltage is not None and parts.voltage is None:
            continue
        ed_score = _edition_score(shot, photo_edition)
        if ed_score == 0:
            continue
        # Prefer exact edition, then voltage-specific pack over generic.
        volt_score = 1 if shot.voltage is not None else 0
        key = (ed_score, volt_score)
        if key > best_key:
            best_key = key
            best = shot
    return best


def _scan_pack(root: Path) -> list[_PackShot]:
    """Index DA/SA ``*.webp`` stems in the pack directory."""
    shots: list[_PackShot] = []
    for path in sorted(root.glob("*.webp")):
        parsed = _parse_stem(path.stem, path)
        if parsed is not None:
            shots.append(parsed)
    return shots


def _upsert_product(
    sku: SKU,
    *,
    stem: str,
    webp: bytes,
    dry_run: bool,
) -> str:
    """Create or update the media-webp product hero; demote other heroes."""
    with transaction.atomic():
        action, image = upsert_sku_image(
            sku,
            source_url=_SOURCE_URL.format(stem=stem),
            filename=f"{sku.sku_code.lower()}-product.webp",
            webp=webp,
            alt=f"{sku.sku_code} | фото привода",
            sort_order=SORT_PRODUCT,
            dry_run=dry_run,
        )
        if not dry_run and image is not None:
            _demote_other_product_shots(sku, keep_pk=image.pk)
    return action


def apply_da_sa_media_webp(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
    assets_root: Path | None = None,
) -> dict[str, Any]:
    """Attach media-webp product heroes to matching DA/SA SKUs.

    The RU DA8/16/24 MQU cutouts live under ``_manuals-ru`` and are attached
    even when the media-webp pack is missing or empty.

    Args:
        dry_run: Count only.
        photo_root: Override pack directory.
        assets_root: Override ``_manuals-ru/DA/assets``. Default is the repo tree.

    Returns:
        Counters: created, updated, skipped, unmatched, missing_root, by_stem,
        manual_heroes.
    """
    root = photo_root or default_media_webp_root()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "unmatched": [],
        "dry_run": dry_run,
        "photo_root": str(root) if root else "",
        "by_stem": {},
    }
    shots: list[_PackShot] = []
    if root is None or not root.is_dir():
        summary["missing_root"] = True
    else:
        shots = _scan_pack(root)
        if not shots:
            summary["skipped"] = 1

    if shots:
        _attach_pack_shots(summary, shots, dry_run=dry_run)

    summary["manual_heroes"] = apply_damqu_manual_heroes(dry_run=dry_run, assets_root=assets_root)
    return summary


def _attach_pack_shots(summary: dict[str, Any], shots: list[_PackShot], *, dry_run: bool) -> None:
    """Write pack heroes onto published DA/SA SKUs. Mutates ``summary``."""
    webp_cache: dict[Path, bytes] = {}
    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^(?:da|sa)\d", is_published=True).order_by(
            "sku_code",
        ),
    )

    for sku in skus:
        parts = _parse_sku(sku.sku_code or "")
        if parts is None:
            summary["skipped"] += 1
            continue
        shot = _pick_shot(parts, shots)
        if shot is None:
            summary["unmatched"].append(sku.sku_code)
            continue
        if shot.path not in webp_cache:
            if dry_run:
                webp_cache[shot.path] = b""
            else:
                webp_cache[shot.path] = convert_bytes_to_webp(
                    shot.path.read_bytes(),
                    quality=DEFAULT_WEBP_QUALITY,
                    max_edge=MAX_EDGE_PX,
                )
        action = _upsert_product(
            sku,
            stem=shot.stem,
            webp=webp_cache[shot.path],
            dry_run=dry_run,
        )
        stem_stats = summary["by_stem"].setdefault(
            shot.stem,
            {"skus": 0, "created": 0, "updated": 0},
        )
        stem_stats["skus"] += 1
        if action == "create":
            summary["created"] += 1
            stem_stats["created"] += 1
        elif action == "update":
            summary["updated"] += 1
            stem_stats["updated"] += 1
        else:
            summary["unchanged"] = summary.get("unchanged", 0) + 1
        logger.info("da_sa_media_webp %s %s ← %s", action, sku.sku_code, shot.stem)


def _damqu_alt_for_target(alt: str, sku_code: str) -> str:
    """Keep a donor caption, but replace a foreign ``DA8MQU…`` label with this SKU."""
    text = (alt or "").strip()
    match = _DAMQU_ALT_MODEL.match(text)
    if match is not None and match.group(1).upper() != sku_code.upper():
        return f"{sku_code}{match.group('rest')}"
    return text or f"{sku_code} | фото привода"


def default_damqu_assets_root() -> Path:
    """RU manual cutouts for the shared DA8/16/24 MQU body."""
    return Path(__file__).resolve().parents[3] / "_manuals-ru" / "DA" / "assets"


def _damqu_asset_dirs(
    *,
    voltage: str,
    edition: str,
    root: Path,
) -> tuple[Path | None, Path | None]:
    """Return (product dir, diagram dir) for this edition.

    24 В on/off has no own folder. Its body photo is the unlabeled 230 В cutout.
    Wiring from 230 В is not reused on 24 В.
    """
    folder_ed = "a-as" if edition in {"a", "as"} else "d-ds"
    exact = root / f"da8-16-24mqu{voltage}-{folder_ed}"
    product = exact if (exact / "product.png").is_file() else None
    diagrams = exact if (exact / "wiring.png").is_file() and (exact / "dimensions.png").is_file() else None
    if product is None and voltage == "24" and folder_ed == "d-ds":
        fallback = root / "da8-16-24mqu230-d-ds"
        if (fallback / "product.png").is_file():
            product = fallback
    return product, diagrams


_DAMQU_CUTOUT_DIR = "da8-16-24mqu-cutout"


def _png_backdrop_is_transparent(path: Path) -> bool:
    """True when the PNG corners are already clear (remove.bg / studio cut-out)."""
    from PIL import Image

    with Image.open(path) as img:
        if img.mode not in ("RGBA", "LA") and not (img.mode == "P" and "transparency" in img.info):
            return False
        rgba = img.convert("RGBA")
    width, height = rgba.size
    if width < 2 or height < 2:
        return False
    corners = (
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
    )
    for point in corners:
        pixel = rgba.getpixel(point)
        if not isinstance(pixel, tuple) or len(pixel) < 4 or int(pixel[3]) >= 16:
            return False
    return True


def _damqu_hero_png(root: Path, product_dir: Path | None) -> Path | None:
    """Prefer the shared remove.bg cut-out over the studio PNG in the manual folder."""
    shared = root / _DAMQU_CUTOUT_DIR / "product.png"
    if shared.is_file():
        return shared
    if product_dir is not None and (product_dir / "product.png").is_file():
        return product_dir / "product.png"
    return None


# Shared remove.bg / Imagine cut-out: lossy WebP 40 keeps alpha and stays light.
_CUTOUT_WEBP_QUALITY = 40


def _png_to_webp(path: Path, *, punch_white: bool = False, quality: int = DEFAULT_WEBP_QUALITY) -> bytes:
    """Encode a manual PNG as WebP.

    Product shots punch the studio white so the theme wash shows through.
    Wiring and dimension drawings stay on paper.
    """
    raw = path.read_bytes()
    if punch_white:
        from io import BytesIO

        from PIL import Image

        from catalog.etl.manual_diagrams import punch_near_white_background

        with Image.open(BytesIO(raw)) as img:
            # Housing face is about luma 75–110; the studio ramp past 115 is the halo.
            punched = punch_near_white_background(img, shadow_luma=115)
        buf = BytesIO()
        punched.save(buf, format="PNG")
        raw = buf.getvalue()
    return convert_bytes_to_webp(raw, quality=quality, max_edge=MAX_EDGE_PX)


def apply_damqu_manual_heroes(
    *,
    dry_run: bool = False,
    assets_root: Path | None = None,
) -> dict[str, Any]:
    """Replace DA8/16/24 MQU heroes with the unlabeled manual product shot.

    The media-webp file ``da10:20mqu`` is a DA10MQU unit marked 8 Нм. The RU
    manual cutout for DA8/16/24 has no foreign article on the housing.

    Returns:
        Counters: heroes, diagrams, alts, missing.
    """
    root = assets_root or default_damqu_assets_root()
    summary: dict[str, Any] = {
        "heroes": 0,
        "diagrams": 0,
        "alts": 0,
        "missing": [],
        "dry_run": dry_run,
    }
    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^da(?:8|16|24)mqu", is_published=True).order_by("sku_code"),
    )
    for sku in skus:
        parsed = _parse_sku(sku.sku_code or "")
        if parsed is None or parsed.nm not in _DAMQU_FAMILY_NM:
            continue
        summary["alts"] += _retarget_damqu_alts(sku, dry_run=dry_run)
        product_dir, diagram_dir = _damqu_asset_dirs(
            voltage=parsed.voltage or "24",
            edition=parsed.edition,
            root=root,
        )
        hero_png = _damqu_hero_png(root, product_dir)
        if hero_png is None:
            summary["missing"].append(sku.sku_code)
            continue
        folder = hero_png.parent.name
        punch = not _png_backdrop_is_transparent(hero_png)
        webp = (
            b""
            if dry_run
            else _png_to_webp(
                hero_png,
                punch_white=punch,
                quality=DEFAULT_WEBP_QUALITY if punch else _CUTOUT_WEBP_QUALITY,
            )
        )
        action, image = upsert_sku_image(
            sku,
            source_url=_DAMQU_MANUAL_SOURCE.format(folder=folder, kind="product"),
            filename=f"{sku.sku_code.lower()}-product.webp",
            webp=webp,
            alt=f"{sku.sku_code} | фото привода",
            sort_order=SORT_PRODUCT,
            dry_run=dry_run,
        )
        if action in {"create", "update"}:
            summary["heroes"] += 1
        if not dry_run and image is not None:
            _demote_other_product_shots(sku, keep_pk=image.pk)
            _unpublish_foreign_damqu_pack(sku)
            ProductImage.objects.filter(
                sku=sku,
                is_published=True,
                source_url__icontains="da8-16-24mqu-da8-16-24mqu",
            ).update(is_published=False)
        if diagram_dir is None:
            continue
        for kind, sort_order, caption in (
            ("wiring", 5, "Схема подключения из инструкции"),
            ("dimensions", 8, "Габаритные размеры привода (мм), чертёж из инструкции"),
        ):
            diagram_webp = b"" if dry_run else _png_to_webp(diagram_dir / f"{kind}.png")
            diagram_action, _ = upsert_sku_image(
                sku,
                source_url=_DAMQU_MANUAL_SOURCE.format(folder=diagram_dir.name, kind=kind),
                filename=f"{sku.sku_code.lower()}-{kind}.webp",
                webp=diagram_webp,
                alt=f"{sku.sku_code} | {caption}",
                sort_order=sort_order,
                dry_run=dry_run,
            )
            if diagram_action in {"create", "update"}:
                summary["diagrams"] += 1
    return summary


def _retarget_damqu_alts(sku: SKU, *, dry_run: bool) -> int:
    """Rewrite cloned ``DA8MQU… |`` captions onto this SKU."""
    changed = 0
    for image in ProductImage.objects.filter(sku=sku, is_published=True):
        new_alt = _damqu_alt_for_target(image.alt or "", sku.sku_code)
        if new_alt == (image.alt or ""):
            continue
        changed += 1
        if not dry_run:
            image.alt = new_alt
            image.save(update_fields=["alt", "updated_at"])
    return changed


def _unpublish_foreign_damqu_pack(sku: SKU) -> int:
    """Hide the labeled da10:20mqu cutout if it is still published on this SKU."""
    qs = ProductImage.objects.filter(sku=sku, is_published=True, source_url__icontains="da10:20mqu")
    count = qs.count()
    if count:
        qs.update(is_published=False)
    return count


def _damqu_edition_tail(sku_code: str) -> tuple[int, str] | None:
    """Return (nm, ``24-A``-style tail) for DA..MQU, else None."""
    match = _DAMQU_EDITION_RE.fullmatch((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm")), match.group("tail").upper()


def _clone_one_image(
    *,
    donor_img: ProductImage,
    target: SKU,
    dry_run: bool,
) -> str:
    """Upsert one gallery row onto ``target`` from ``donor_img`` bytes.

    Only published donor photos are cloned; a rerun with the same bytes is a
    ``skipped`` (no storage write).
    """
    if not donor_img.is_published or not donor_img.image:
        return "skipped"
    if "da10:20mqu" in (donor_img.source_url or "").casefold():
        return "skipped"
    donor_img.image.open("rb")
    try:
        payload = donor_img.image.read()
    finally:
        donor_img.image.close()
    if not payload:
        return "skipped"
    stem = Path(donor_img.image.name or "photo.webp").name
    source_url = (donor_img.source_url or "").strip() or _CLONE_SOURCE_URL.format(stem=stem)
    action, _ = upsert_sku_image(
        target,
        source_url=source_url,
        filename=f"{target.sku_code.lower()}-{stem}",
        webp=payload,
        alt=_damqu_alt_for_target(donor_img.alt or "", target.sku_code),
        sort_order=donor_img.sort_order,
        dry_run=dry_run,
    )
    return "skipped" if action == "skip" else action


def clone_damqu_images_from_donor(
    *,
    donor_nm: int = 8,
    target_nms: tuple[int, ...] = (16, 24),
    dry_run: bool = False,
) -> dict[str, Any]:
    """Copy ProductImage rows from DA{donor}MQU onto DA16/DA24 same editions.

    The three torques share one body. The labeled ``da10:20mqu`` cutout is not
    copied. Useful when DA8 already has the manual shots and the pack is absent.

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
            "images",
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
        for img in donor.images.all():
            action = _clone_one_image(donor_img=img, target=target, dry_run=dry_run)
            if action == "create":
                summary["created"] += 1
            elif action == "update":
                summary["updated"] += 1
            else:
                summary["skipped"] += 1
    return summary
