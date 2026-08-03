"""Attach per-SKU HVA/HVD heroes from the studio pack (unique photo per code).

Source (Yandex Disk)::

    ~/Yandex.Disk.localized/фото для сайта/弹簧复位产品/
        HVD24S-5F.png          # perspective (square product)
        HVD230-40.png          # frontal PNG (tall)
        HVD230-40QX.tif        # frontal TIFF (all ``.tif`` are frontal)
        front/HVD24S-5F A.png  # skipped (duplicate frontal angles)

Preference per SKU::

    1. perspective / product shot (aspect < 1.35)
    2. F-family sibling perspective when exact file is frontal
    3. frontal PNG/TIFF when no perspective exists for that code
    4. QX → matching Q (same preference order)

Files are cutouts (PNG often RGBA; TIFF often opaque RGB). We trim by alpha,
center on the shared catalog canvas with the HV Nm hierarchy, re-encode WebP,
and upsert ``sort_order=0`` (demoting shared media-webp / Tilda heroes).
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image

from catalog.etl.hv_media_webp import _demote_other_product_shots
from catalog.etl.manual_diagrams import CATALOG_HERO_CANVAS, CATALOG_HERO_MARGIN
from catalog.etl.webp import (
    DEFAULT_WEBP_QUALITY,
    WEBP_METHOD,
    trim_rgba_padding,
)
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

SORT_PRODUCT: Final[int] = 0
_SOURCE_URL = "https://hoocon.ru/.local-assets/hv-sku/{code}-product.webp"

_DEFAULT_ROOTS: Final[tuple[Path, ...]] = (
    Path.home() / "Yandex.Disk.localized/фото для сайта/弹簧复位产品",
    Path.home() / "Yandex.Disk.localized/фото для сайта/HV 产品(1)/HV 产品",
)
_DEFAULT_SPRING_ROOTS: Final[tuple[Path, ...]] = (Path.home() / "Yandex.Disk.localized/фото для сайта/弹簧复位产品",)

_HV_SKU_STEM = re.compile(
    r"(?i)^(?P<code>hv[ad](?:24|230)s?(?:t)?-\d+(?:qx|qa|q|p|f|e)?)$",
)
_HV_NM = re.compile(r"(?i)^hv[ad](?:24|230)s?(?:t)?-(?P<nm>\d+)(?P<sfx>qx|qa|q|p|f|e)?$")
_REF_NM: Final[int] = 40
_REF_NM_F: Final[int] = 5
_MIN_SCALE: Final[float] = 0.75


def default_hv_sku_photo_root() -> Path | None:
    """First existing HV-per-SKU studio directory, if any."""
    for root in _DEFAULT_ROOTS:
        if root.is_dir():
            return root
    return None


def default_hv_spring_photo_root() -> Path | None:
    """First existing HVA/HVD spring-return (``*P``) studio directory, if any."""
    for root in _DEFAULT_SPRING_ROOTS:
        if root.is_dir():
            return root
    return None


def hv_nm_canvas_factor(nm: int, *, is_fire: bool = False) -> float:
    """Relative long-side scale (air REF=40 Нм; HVD-…F REF=5 Нм)."""
    if nm <= 0:
        return 1.0
    ref = _REF_NM_F if is_fire else _REF_NM
    return _MIN_SCALE + (1.0 - _MIN_SCALE) * (min(nm, ref) / float(ref))


def parse_hv_nm(sku_code: str) -> int | None:
    """Rated torque from an HVA/HVD edition code."""
    match = _HV_NM.match((sku_code or "").strip())
    if match is None:
        return None
    return int(match.group("nm"))


def _is_hv_fire_sku(sku_code: str) -> bool:
    """True for HVD smoke/fire ``…-{nm}F`` editions."""
    return bool(re.search(r"(?i)-\d+f$", (sku_code or "").strip()))


def _stem_to_sku_code(stem: str) -> str | None:
    """Normalize a filename stem to a catalog SKU code (drop `` A`` angle mark)."""
    clean = re.sub(r"(?i)\s+a$", "", (stem or "").strip())
    clean = clean.replace(" ", "")
    match = _HV_SKU_STEM.match(clean)
    if match is None:
        return None
    return match.group("code").upper()


def _is_angle_stem(stem: str) -> bool:
    """True for ``… A`` / front-folder alternate angle filenames."""
    return bool(re.search(r"(?i)\s+a$", (stem or "").strip()))


_IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".png", ".webp", ".jpg", ".jpeg", ".tif", ".tiff"},
)


def iter_hv_sku_photo_files(root: Path, *, skip_front: bool = True) -> list[tuple[str, Path, bool]]:
    """Collect ``(sku_code, path, is_angle)`` from a studio tree.

    Args:
        root: Studio directory.
        skip_front: Ignore ``front/`` subfolder (duplicate frontal angles).
    """
    rows: list[tuple[str, Path, bool]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if skip_front and "front" in {part.casefold() for part in path.relative_to(root).parts[:-1]}:
            continue
        if path.suffix.casefold() not in _IMAGE_SUFFIXES:
            continue
        if path.name.startswith("."):
            continue
        code = _stem_to_sku_code(path.stem)
        if code is None:
            continue
        rows.append((code, path, _is_angle_stem(path.stem)))
    return rows


def _center_alpha_cutout_on_canvas(
    image: Image.Image,
    *,
    factor: float,
    canvas_size: tuple[int, int] = CATALOG_HERO_CANVAS,
    margin: float = CATALOG_HERO_MARGIN,
) -> Image.Image:
    """Trim transparent pad (keep black housing) and center with Nm factor."""
    canvas_w, canvas_h = canvas_size
    inner_w = int(canvas_w * (1 - 2 * margin))
    inner_h = int(canvas_h * (1 - 2 * margin))
    rgba = trim_rgba_padding(image.convert("RGBA"), pad_px=4)
    cw, ch = rgba.size
    fit = min(inner_w / cw, inner_h / ch) * max(0.01, min(factor, 1.0))
    nw, nh = max(1, int(cw * fit)), max(1, int(ch * fit))
    if nw > inner_w or nh > inner_h:
        s2 = min(inner_w / nw, inner_h / nh)
        nw, nh = max(1, int(nw * s2)), max(1, int(nh * s2))
    resized = rgba.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    canvas.paste(resized, ((canvas_w - nw) // 2, (canvas_h - nh) // 2), resized)
    return canvas


def punch_near_black_background(
    image: Image.Image,
    *,
    luma_max: int = 40,
) -> Image.Image:
    """Make edge-connected near-black pixels transparent (studio cutout).

    Flood-fills from the border so black faceplates / labels on the product
    stay opaque when surrounded by lighter housing.

    Args:
        image: RGB/RGBA cutout.
        luma_max: Maximum average channel value treated as backdrop.

    Returns:
        RGBA with transparent studio backdrop.
    """
    from collections import deque
    from typing import Any, cast

    rgba = image.convert("RGBA")
    pixels = cast(Any, rgba.load())
    width, height = rgba.size
    if width < 2 or height < 2 or pixels is None:
        return rgba

    def is_backdrop(x: int, y: int) -> bool:
        r, g, b, a = pixels[x, y]
        if a < 16:
            return True
        # Studio pads are often semi-transparent near-black (alpha ~100).
        if (r + g + b) / 3 > luma_max:
            return False
        return max(r, g, b) <= luma_max + 25

    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def try_enqueue(x: int, y: int) -> None:
        if x < 0 or y < 0 or x >= width or y >= height:
            return
        index = y * width + x
        if seen[index]:
            return
        if not is_backdrop(x, y):
            return
        seen[index] = 1
        queue.append((x, y))

    for x in range(width):
        try_enqueue(x, 0)
        try_enqueue(x, height - 1)
    for y in range(height):
        try_enqueue(0, y)
        try_enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        pixels[x, y] = (0, 0, 0, 0)
        try_enqueue(x + 1, y)
        try_enqueue(x - 1, y)
        try_enqueue(x, y + 1)
        try_enqueue(x, y - 1)

    return rgba


def prepare_hv_sku_hero_webp(path: Path, *, sku_code: str) -> bytes:
    """Load a studio cutout (PNG/TIFF/…), canvas-normalize, return WebP bytes.

    Black faceplates must stay opaque — do not flood-punch near-black (that
    eats HVD-…F panels via edge-connected cables/trim). PNG sources often have
    transparent pads; frontal TIFF is usually opaque RGB — we only trim alpha
    and center on the catalog canvas.
    """
    nm = parse_hv_nm(sku_code) or (_REF_NM_F if _is_hv_fire_sku(sku_code) else _REF_NM)
    factor = hv_nm_canvas_factor(nm, is_fire=_is_hv_fire_sku(sku_code))
    with Image.open(path) as img:
        img.load()
        rgba = img.convert("RGBA")
        canvas = _center_alpha_cutout_on_canvas(rgba, factor=factor)
    buf = BytesIO()
    canvas.save(buf, format="WEBP", quality=DEFAULT_WEBP_QUALITY, method=WEBP_METHOD)
    # Already on catalog canvas (≤2076); skip second max-edge shrink that softens text.
    return buf.getvalue()


def _qx_fallback_code(sku_code: str) -> str | None:
    """Map capacitor QX editions to the matching Q studio shot."""
    code = (sku_code or "").strip().upper()
    if not code.endswith("QX"):
        return None
    return f"{code[:-2]}Q"


def _is_frontal_shot(path: Path) -> bool:
    """True for frontal studio shots (all TIFF; tall PNG crops aspect ≥ 1.35)."""
    if path.suffix.casefold() in {".tif", ".tiff"}:
        return True
    try:
        with Image.open(path) as img:
            width, height = img.size
    except OSError:
        return False
    if width < 1:
        return False
    return (height / float(width)) >= 1.35


# Back-compat alias used in tests / callers.
_is_faceplate_style = _is_frontal_shot


def _product_shot_fallback(code: str, perspective_map: dict[str, Path]) -> tuple[str, Path] | None:
    """Prefer a perspective shot from the same F family when the exact file is frontal."""
    match = re.match(r"(?i)^(hvd)(24|230)(s|st)-(\d+f)$", code)
    if match is None:
        return None
    series, volt, aux, nm = match.groups()
    other_volt = "230" if volt == "24" else "24"
    alt_aux = "ST" if aux.lower() == "s" else "S"
    candidates = [
        f"{series.upper()}{other_volt}{aux.upper()}-{nm.upper()}",
        f"{series.upper()}{volt}{alt_aux}-{nm.upper()}",
        f"{series.upper()}{other_volt}{alt_aux}-{nm.upper()}",
    ]
    for cand in candidates:
        path = perspective_map.get(cand)
        if path is not None:
            return cand, path
    return None


def _resolve_studio_source(
    code: str,
    *,
    perspective_map: dict[str, Path],
    frontal_map: dict[str, Path],
    allow_qx_fallback: bool,
) -> tuple[str, Path, bool] | None:
    """Pick ``(source_label, path, is_frontal)`` for a SKU code.

    Perspective first; frontal PNG/TIFF only when no perspective exists.
    """
    if code in perspective_map:
        return code, perspective_map[code], False
    sibling = _product_shot_fallback(code, perspective_map)
    if sibling is not None:
        return sibling[0], sibling[1], False
    if code in frontal_map:
        return code, frontal_map[code], True
    if not allow_qx_fallback:
        return None
    q_code = _qx_fallback_code(code)
    if q_code is None:
        return None
    if q_code in perspective_map:
        return q_code, perspective_map[q_code], False
    if q_code in frontal_map:
        return q_code, frontal_map[q_code], True
    return None


def _upsert_sku_image(
    sku: SKU,
    *,
    webp: bytes,
    source_url: str,
    alt: str,
    filename: str,
    sort_order: int,
    demote_others: bool,
    dry_run: bool,
) -> str:
    """Create/update one ProductImage row for a SKU photo."""
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return "update" if existing else "create"

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
            keep_pk = image.pk
            action = "create"
        else:
            existing.alt = alt[:300]
            existing.sort_order = sort_order
            existing.is_published = True
            existing.image.save(filename, ContentFile(webp), save=False)
            existing.full_clean()
            existing.save()
            keep_pk = existing.pk
            action = "update"
        if demote_others:
            _demote_other_product_shots(sku, keep_pk=keep_pk)
    return action


def apply_hv_sku_media(
    *,
    dry_run: bool = False,
    photo_root: Path | None = None,
    include_spring: bool = False,
    spring_root: Path | None = None,
    only_missing: bool = False,
) -> dict[str, Any]:
    """Attach unique per-SKU heroes from the HV studio pack.

    Args:
        dry_run: Count only.
        photo_root: Override HV 产品 tree.
        include_spring: Also scan the ``*P`` spring-return folder.
        spring_root: Override spring-return directory.
        only_missing: Attach only when an exact studio file exists and the SKU
            does not yet have a published ``hv-sku/{code}-product`` hero
            (no QX→Q fallback).

    Returns:
        Counters and unmatched file stems.
    """
    root = photo_root if photo_root is not None else default_hv_sku_photo_root()
    summary: dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "frontal_fallback": 0,
        "already_own": 0,
        "missing_sku": [],
        "qx_fallback": 0,
        "dry_run": dry_run,
        "only_missing": only_missing,
        "photo_root": str(root) if root else "",
        "spring_root": "",
    }
    perspective_map: dict[str, Path] = {}
    frontal_map: dict[str, Path] = {}

    roots: list[Path] = []
    if root is not None:
        roots.append(root)
    if include_spring:
        sroot = spring_root if spring_root is not None else default_hv_spring_photo_root()
        if sroot is not None:
            summary["spring_root"] = str(sroot)
            roots.append(sroot)

    if not roots:
        summary["missing_sku"].append("(root not found)")
        return summary

    for tree in roots:
        for code, path, is_angle in iter_hv_sku_photo_files(tree, skip_front=True):
            # Skip front/ and ``… A`` duplicate frontal angles.
            if is_angle:
                continue
            if _is_frontal_shot(path):
                frontal_map.setdefault(code, path)
            else:
                perspective_map.setdefault(code, path)

    skus = {
        (sku.sku_code or "").strip().upper(): sku
        for sku in SKU.objects.filter(sku_code__iregex=r"(?i)^hv[ad]", is_published=True)
    }

    # Prefer perspective; frontal PNG/TIFF when no perspective for that code.
    attach_plan: list[tuple[SKU, Path, str]] = []
    used_files: set[str] = set()
    for code, sku in sorted(skus.items()):
        own_url = _SOURCE_URL.format(code=code.lower())
        has_own = ProductImage.objects.filter(
            sku=sku,
            source_url=own_url,
            is_published=True,
        ).exists()
        if only_missing and has_own:
            summary["already_own"] += 1
            continue

        resolved = _resolve_studio_source(
            code,
            perspective_map=perspective_map,
            frontal_map=frontal_map,
            allow_qx_fallback=not only_missing,
        )
        if resolved is None:
            continue
        source_label, path, is_frontal = resolved
        if is_frontal:
            summary["frontal_fallback"] += 1
        q_code = _qx_fallback_code(code)
        if q_code is not None and source_label == q_code:
            summary["qx_fallback"] += 1
        attach_plan.append((sku, path, source_label))
        used_files.add(source_label)

    for code in sorted({*perspective_map, *frontal_map}):
        if code not in used_files and code not in skus:
            summary["missing_sku"].append(code)

    webp_cache: dict[Path, bytes] = {}
    for sku, path, source_label in attach_plan:
        code = (sku.sku_code or "").strip().upper()
        if dry_run:
            existing = ProductImage.objects.filter(
                sku=sku,
                source_url=_SOURCE_URL.format(code=code.lower()),
            ).exists()
            if existing:
                summary["updated"] += 1
            else:
                summary["created"] += 1
            continue
        try:
            if path not in webp_cache:
                webp_cache[path] = prepare_hv_sku_hero_webp(path, sku_code=code)
            webp = webp_cache[path]
        except OSError as exc:
            logger.warning("hv_sku_media skip %s: %s", path, exc)
            summary["skipped"] += 1
            continue
        source_url = _SOURCE_URL.format(code=code.lower())
        alt = f"{code} | фото привода"
        action = _upsert_sku_image(
            sku,
            webp=webp,
            source_url=source_url,
            alt=alt,
            filename=f"{code.lower()}-product.webp",
            sort_order=SORT_PRODUCT,
            demote_others=True,
            dry_run=False,
        )
        if action == "create":
            summary["created"] += 1
        else:
            summary["updated"] += 1
        logger.info("hv_sku_media %s %s ← %s", action, code, path.name)

    summary["missing_sku"] = sorted(set(summary["missing_sku"]))
    summary["attached"] = summary["created"] + summary["updated"]
    return summary
