"""Canonical copy + ТТХ for all Hoocon BV* ball valves (BV215 template).

Source: sibling Tilda store CSV
``../hoocon/docs/выгрузка/store-12190035-SHarovie_krani-*.csv``
and PDP pages on hoocon.ru. Style: docs/tech-copy-belimo-ru.md.
"""

from __future__ import annotations

import csv
import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.attr_groups import (
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_HYDRAULIC,
    ATTR_GROUP_MATERIALS,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
    ATTR_GROUP_VALVE,
)
from catalog.etl.tech_copy import normalize_tech_copy
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, convert_bytes_to_webp
from catalog.models import SKU, Attribute, AttributeValue, Product, ProductImage

logger = logging.getLogger(__name__)

DEFAULT_STORE_CSV = (
    Path(__file__).resolve().parents[3]
    / ".."
    / "hoocon"
    / "docs"
    / "выгрузка"
    / "store-12190035-SHarovie_krani-202604281115.csv"
)

_FU_SERIES_RE = re.compile(r"(?i)da\d*fu")
_SERIES_RE = re.compile(r"\b(BV\d{3})\b", re.I)
_SKU_EDITION_RE = re.compile(r"(?i)bv(\d{3})([a-e])\s*$")
_DN_RE = re.compile(r"DN\s*(\d+)", re.I)

AttrRow = tuple[str, str, str, str, str]


def format_compatible_actuators(series: tuple[str, ...]) -> str:
    """Build «совместимый привод» value (drives only, no bracket)."""
    return f"{', '.join(series)} (−D/−DS/−A/−AS)"


def format_bracket(series: tuple[str, ...]) -> str:
    """Build «кронштейн»; BR-ML only when DA…FU is listed."""
    if any(_FU_SERIES_RE.search(item) for item in series):
        return "BR-M / BR-ML (для DA…FU)"
    return "BR-M"


def product_slug_for_series(series: str) -> str:
    """Return CMS product slug for a BV code (e.g. BV220 → sharovoy-kran-bv220)."""
    return f"sharovoy-kran-{series.casefold()}"


def ball_valve_product_slugs() -> frozenset[str]:
    """All known ball-valve product slugs (canonical card series)."""
    return frozenset(
        product_slug_for_series(f"BV{n}")
        for n in (
            215,
            220,
            225,
            232,
            240,
            250,
            315,
            320,
            325,
            332,
            340,
            350,
        )
    )


@dataclass(frozen=True)
class BallValveSeries:
    """One BV* parent + editions from the Tilda store export."""

    code: str
    product_slug: str
    product_name: str
    ways: str
    dn: str
    thread: str
    drive_series: tuple[str, ...]
    gallery_urls: tuple[str, ...]
    kvs_by_edition: dict[str, str]
    height_actuator: str
    height_stem: str
    valve_length: str
    valve_od: str
    center_to_edge: str
    diff_pressure: str

    @property
    def compatible_actuators(self) -> str:
        return format_compatible_actuators(self.drive_series)

    @property
    def bracket(self) -> str:
        return format_bracket(self.drive_series)

    @property
    def voltage_label(self) -> str:
        """Nominal actuator voltage from series family (BV2xx=24, BV3xx=230)."""
        return "230 В" if self.code.upper().startswith("BV3") else "24 В"


def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(html.unescape(text).split())


def _parse_tech_table(tabs2: str) -> dict[str, str]:
    body = tabs2.split("|#|", 2)[-1] if "|#|" in tabs2 else tabs2
    out: dict[str, str] = {}
    for match in re.finditer(
        r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>",
        body,
        flags=re.I | re.S,
    ):
        key = _strip_html(match.group(1)).rstrip(":")
        out[key] = _strip_html(match.group(2))
    return out


def _mm(value: str) -> str:
    return re.sub(r"\s*мм\s*$", "", value, flags=re.I).strip()


def _mpa(value: str) -> str:
    return re.sub(r"\s*МПа\s*$", "", value, flags=re.I).strip()


def _normalize_title(title: str) -> str:
    """Canonical PDP H1: ``BV220 | Шаровой кран 2-ходовый DN 20``."""
    text = " ".join((title or "").split())
    text = re.sub(r"\bDN\s*(\d+)\b", r"DN \1", text, flags=re.I)
    return text


def _drive_families_from_mods(modifications: str) -> list[str]:
    """Parse drive base codes from Tilda «Modifications» configurator field.

    Typical shape: ``Выбор привода:…|Выбор кронштейна:…``. The marker may
    appear in any ``|``-separated segment — locate that segment first.
    """
    marker = "Выбор привода:"
    if marker not in modifications:
        return []
    segment = next(
        (part for part in modifications.split("|") if marker in part),
        "",
    )
    if not segment:
        return []
    _, sep, after = segment.partition(marker)
    if not sep:
        return []
    families: list[str] = []
    seen: set[str] = set()
    for opt in after.split(";"):
        raw = opt.strip()
        if not raw or raw == "Не выбран":
            continue
        base = raw.split("-", 1)[0].upper()
        if base in seen:
            continue
        seen.add(base)
        families.append(base)
    return families


def _drive_families_from_tabs1(tabs1: str) -> list[str]:
    """Parse «Электропривод» bullet list from Tabs:1 (matches live PDP)."""
    text = re.sub(r"<[^>]+>", " ", tabs1 or "")
    text = html.unescape(text)
    match = re.search(
        r"Электропривод\s*:?(.*?)(?:Гарантия|Применение|$)",
        text,
        flags=re.I | re.S,
    )
    chunk = match.group(1) if match else ""
    families: list[str] = []
    seen: set[str] = set()
    for opt in re.findall(r"da[0-9a-z]+", chunk, flags=re.I):
        base = opt.split("-", 1)[0].upper()
        if base in seen:
            continue
        seen.add(base)
        families.append(base)
    return families


def _drive_families(modifications: str, tabs1: str = "") -> tuple[str, ...]:
    """Union of Tabs:1 (PDP copy) and store Modifications configurator."""
    from_tabs = _drive_families_from_tabs1(tabs1)
    from_mods = _drive_families_from_mods(modifications)
    seen: set[str] = set()
    families: list[str] = []
    for base in (*from_tabs, *from_mods):
        if base in seen:
            continue
        seen.add(base)
        families.append(base)
    # Drop Tilda typo DA5FU30 when DA5FU230 is already listed.
    if any(re.fullmatch(r"DA\d+FU230", f) for f in families):
        families = [f for f in families if not re.fullmatch(r"DA\d+FU30", f)]
    return tuple(sorted(families))


def _kvs_from_editions(edition_rows: list[dict[str, str]]) -> dict[str, str]:
    by_letter: dict[str, str] = {}
    for row in edition_rows:
        sku = (row.get("SKU") or "").strip()
        match = _SKU_EDITION_RE.search(sku)
        if not match:
            continue
        letter = match.group(2).lower()
        editions = row.get("Editions") or ""
        kvs_match = re.search(r"KVS[^:]*:\s*([0-9,]+)", editions, flags=re.I)
        if kvs_match:
            by_letter[letter] = kvs_match.group(1).strip()
    return by_letter


def load_ball_valve_series(csv_path: Path | None = None) -> list[BallValveSeries]:
    """Parse Tilda store CSV into BV* series specs.

    Args:
        csv_path: Optional override; default is the sibling hoocon export.

    Returns:
        Sorted list of series (BV215, BV220, …).

    Raises:
        FileNotFoundError: if CSV is missing.
    """
    path = (csv_path or DEFAULT_STORE_CSV).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Ball-valve store CSV not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))

    parents: dict[str, dict[str, str]] = {}
    editions: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        title = row.get("Title") or ""
        match = _SERIES_RE.search(title)
        if not match:
            continue
        code = match.group(1).upper()
        sku = (row.get("SKU") or "").strip()
        if not sku:
            parents[code] = row
        else:
            editions.setdefault(code, []).append(row)

    result: list[BallValveSeries] = []
    for code, parent in sorted(parents.items()):
        tech = _parse_tech_table(parent.get("Tabs:2") or "")
        title = _normalize_title(parent.get("Title") or code)
        dn_raw = tech.get("Диаметр шарового крана", "")
        dn_match = _DN_RE.search(dn_raw) or _DN_RE.search(title)
        dn = dn_match.group(1) if dn_match else ""
        ways = "3-ходовый" if "3-ходовый" in title else "2-ходовый"
        thread_raw = tech.get("Резьба внутренняя", "").strip()
        thread = f"внутренняя {thread_raw}" if thread_raw else ""
        photos = tuple(u for u in (parent.get("Photo") or "").split() if u.startswith("http"))
        center = tech.get("Длина от центра до края крана (для 3-ходового)", "")
        center_val = "" if center in {"", "—", "-"} else _mm(center)
        result.append(
            BallValveSeries(
                code=code,
                product_slug=product_slug_for_series(code),
                product_name=title,
                ways=ways,
                dn=dn,
                thread=thread,
                drive_series=_drive_families(
                    parent.get("Modifications") or "",
                    parent.get("Tabs:1") or "",
                ),
                gallery_urls=photos,
                kvs_by_edition=_kvs_from_editions(editions.get(code, [])),
                height_actuator=_mm(
                    tech.get(
                        "Высота от центра крана до верхнего края привода",
                        "",
                    ),
                ),
                height_stem=_mm(
                    tech.get(
                        "Высота от центра крана до верхнего края штока",
                        "",
                    ),
                ),
                valve_length=_mm(tech.get("Длина крана", "")),
                valve_od=_mm(tech.get("Внешний диаметр крана", "")),
                center_to_edge=center_val,
                diff_pressure=_diff_pressure_mpa(
                    tech.get("Максимальный рабочий перепад давления"),
                ),
            ),
        )
    return result


def _diff_pressure_mpa(raw: str | None, *, default: str = "0,35") -> str:
    """Normalize differential pressure; default only when value is missing/blank.

    Args:
        raw: Table cell text (may include «МПа») or None if key absent.
        default: Used when the field is missing or whitespace-only.

    Returns:
        Numeric string without the unit suffix.
    """
    if raw is None or not str(raw).strip():
        return default
    return _mpa(str(raw))


def kvs_for_sku(series: BallValveSeries, sku_code: str) -> str | None:
    """Return Kvs for an edition SKU of this series."""
    match = _SKU_EDITION_RE.search((sku_code or "").strip())
    if not match:
        return None
    # series.code is «BV215»; strip prefix so we compare «215» to «215».
    series_num = series.code.upper().removeprefix("BV")
    if match.group(1) != series_num:
        return None
    return series.kvs_by_edition.get(match.group(2).lower())


def _series_description(series: BallValveSeries) -> str:
    return normalize_tech_copy(
        f"""
Шаровой кран {series.ways} DN {series.dn} серии {series.code} для систем
отопления, вентиляции и кондиционирования (HVAC).

Назначение и особенности:
– Рабочая среда (по умолчанию): холодная и горячая вода;
  по спецзаказу — с содержанием этиленгликоля не более 50 %.
– Рабочая температура среды: –9…+95 °C.
– Резьба: {series.thread}.
– Вид: {series.ways}.
– Совместимый привод {series.voltage_label}: {series.compatible_actuators}.
– Кронштейн: {series.bracket}.
– Гарантия: 24 месяца.

Область применения:
– Системы обработки воздуха.
– VAV-системы вентиляции и осушения (фанкойлы).
– Вентиляционные установки.
– Воздухоподогреватели.
– Крышные кондиционеры.
– Бойлерные системы (чиллеры).
""".strip(),
    )


def _sku_description(series: BallValveSeries, kvs: str) -> str:
    lines = [
        (
            f"Шаровой кран {series.ways} DN {series.dn} серии "
            f"{series.code} для систем отопления, вентиляции "
            "и кондиционирования (HVAC)."
        ),
        f"Пропускная способность: Kvs {kvs} м³/ч.",
        (
            "Рабочая среда — холодная и горячая вода "
            "(этиленгликоль ≤ 50 % по спецзаказу); "
            f"температура среды –9…+95 °C; "
            f"резьба {series.thread}."
        ),
        "",
        "Область применения:",
        "– Системы обработки воздуха.",
        "– VAV-системы вентиляции и осушения (фанкойлы).",
        "– Вентиляционные установки.",
        "– Воздухоподогреватели.",
        "– Крышные кондиционеры.",
        "– Бойлерные системы (чиллеры).",
        "",
        f"Совместимый привод: {series.compatible_actuators}.",
        f"Кронштейн: {series.bracket}.",
        "Гарантия: 24 месяца.",
    ]
    return normalize_tech_copy("\n".join(lines))


def _shared_attrs(series: BallValveSeries) -> tuple[AttrRow, ...]:
    rows: list[AttrRow] = [
        ("DN", "dn", "", series.dn, ATTR_GROUP_VALVE),
        ("Вид крана", "ways", "", series.ways, ATTR_GROUP_VALVE),
        ("Резьба", "thread", "", series.thread, ATTR_GROUP_VALVE),
        (
            "Максимальный рабочий перепад давления",
            "diff-pressure",
            "МПа",
            series.diff_pressure,
            ATTR_GROUP_HYDRAULIC,
        ),
        (
            "Рабочая среда",
            "medium",
            "",
            "холодная и горячая вода (этиленгликоль ≤ 50 % по спецзаказу)",
            ATTR_GROUP_OPERATING,
        ),
        (
            "Рабочая температура среды",
            "media-temp",
            "°C",
            "–9…+95",
            ATTR_GROUP_OPERATING,
        ),
        ("Угол поворота", "rotation-angle", "°", "0…90", ATTR_GROUP_FUNCTIONAL),
        ("Материал корпуса", "material", "", "Латунь", ATTR_GROUP_MATERIALS),
        (
            "Золотниковый шток и шар",
            "ball-stem-material",
            "",
            "Нержавеющая сталь 304",
            ATTR_GROUP_MATERIALS,
        ),
        (
            "Двойное уплотнение штока",
            "stem-seal",
            "",
            "Прокладка из каучука (EPDM)",
            ATTR_GROUP_MATERIALS,
        ),
        (
            "Уплотнение корпуса крана",
            "seat-seal",
            "",
            "Фторопласт (PTFE)",
            ATTR_GROUP_MATERIALS,
        ),
        (
            "Выпрямительный диск",
            "flow-disk",
            "",
            "Встроенный цельный",
            ATTR_GROUP_MATERIALS,
        ),
        (
            "Высота до верхнего края привода",
            "height-actuator",
            "мм",
            series.height_actuator,
            ATTR_GROUP_SIZE,
        ),
        (
            "Высота до верхнего края штока",
            "height-stem",
            "мм",
            series.height_stem,
            ATTR_GROUP_SIZE,
        ),
        (
            "Длина крана",
            "valve-length",
            "мм",
            series.valve_length,
            ATTR_GROUP_SIZE,
        ),
        (
            "Внешний диаметр крана",
            "valve-od",
            "мм",
            series.valve_od,
            ATTR_GROUP_SIZE,
        ),
    ]
    if series.center_to_edge:
        rows.append(
            (
                "Длина от центра до края крана",
                "center-to-edge",
                "мм",
                series.center_to_edge,
                ATTR_GROUP_SIZE,
            ),
        )
    return tuple(rows)


def _ensure_attr(name: str, slug: str, unit: str) -> Attribute:
    attr, _ = Attribute.objects.get_or_create(
        slug=slug,
        defaults={"name": name, "unit": unit},
    )
    if attr.name != name or attr.unit != unit:
        attr.name = name
        attr.unit = unit
        attr.save(update_fields=["name", "unit"])
    return attr


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    attr = _ensure_attr(name, slug, unit)
    AttributeValue.objects.update_or_create(
        sku=sku,
        attribute=attr,
        defaults={"value": value},
    )


def attach_gallery_images(
    sku: SKU,
    urls: tuple[str, ...],
    *,
    alt_prefix: str,
    quality: int = DEFAULT_WEBP_QUALITY,
    dry_run: bool = False,
) -> dict[str, int]:
    """Download Tilda CDN gallery onto SKU (idempotent by source_url)."""
    from catalog.management.commands.import_tilda_images import _download

    created = 0
    existing = 0
    failed = 0
    for sort_order, url in enumerate(urls):
        if ProductImage.objects.filter(sku=sku, source_url=url).exists():
            existing += 1
            ProductImage.objects.filter(sku=sku, source_url=url).update(
                sort_order=sort_order,
                is_published=True,
            )
            continue
        if dry_run:
            created += 1
            continue
        try:
            raw = _download(url)
            webp = convert_bytes_to_webp(raw, quality=quality)
            filename = f"{sku.sku_code.lower()}-{sort_order}.webp"
            with transaction.atomic():
                img = ProductImage(
                    sku=sku,
                    alt=f"{alt_prefix} — фото {sort_order + 1}"[:300],
                    source_url=url,
                    sort_order=sort_order,
                    is_published=True,
                )
                img.image.save(filename, ContentFile(webp), save=False)
                img.full_clean()
                img.save()
            created += 1
        except (HTTPError, URLError, OSError, ValueError, ValidationError) as exc:
            failed += 1
            logger.warning(
                "Ball valve image fail %s %s: %s",
                sku.sku_code,
                url,
                exc,
            )
    return {"created": created, "existing": existing, "failed": failed}


def apply_series_enrichment(
    series: BallValveSeries,
    *,
    import_images: bool = True,
) -> dict[str, int]:
    """Rewrite one BV* product/SKUs: copy, ТТХ cards, gallery."""
    product = Product.objects.filter(slug=series.product_slug).first()
    if product is None:
        return {
            "products": 0,
            "skus": 0,
            "attributes": 0,
            "images_created": 0,
            "images_failed": 0,
        }

    product.name = series.product_name[:200]
    product.description = _series_description(series)
    product.specs_text = ""
    product.save(update_fields=["name", "description", "specs_text"])

    skus = list(SKU.objects.filter(product=product).order_by("sku_code"))
    attrs = 0
    images_created = 0
    images_failed = 0
    shared = _shared_attrs(series)

    for sku in skus:
        kvs = kvs_for_sku(series, sku.sku_code)
        if not kvs:
            logger.warning(
                "%s skip unknown edition: %s",
                series.code,
                sku.sku_code,
            )
            continue

        sku.name = series.product_name[:300]
        sku.description = _sku_description(series, kvs)
        sku.specs_text = ""
        sku.save(update_fields=["name", "description", "specs_text"])

        AttributeValue.objects.filter(sku=sku).delete()
        for name, slug, unit, value, _group in shared:
            if not value:
                continue
            _set_attr(sku, name, slug, unit, value)
            attrs += 1
        _set_attr(sku, "Kvs", "kvs", "м³/ч", kvs)
        attrs += 1
        _set_attr(
            sku,
            "Совместимый привод",
            "compatible-actuators",
            "",
            series.compatible_actuators,
        )
        attrs += 1
        _set_attr(sku, "Кронштейн", "bracket", "", series.bracket)
        attrs += 1

        if import_images and series.gallery_urls:
            img_stats = attach_gallery_images(
                sku,
                series.gallery_urls,
                alt_prefix=series.product_name,
            )
            images_created += img_stats["created"]
            images_failed += img_stats["failed"]

    return {
        "products": 1,
        "skus": len(skus),
        "attributes": attrs,
        "images_created": images_created,
        "images_failed": images_failed,
    }


def apply_all_ball_valve_enrichment(
    *,
    import_images: bool = True,
    series_codes: tuple[str, ...] | None = None,
    csv_path: Path | None = None,
) -> dict[str, int]:
    """Enrich all (or selected) BV* series from the store CSV.

    Args:
        import_images: Download parent galleries.
        series_codes: Optional filter like ``("BV220", "BV315")``.
        csv_path: Optional CSV override.

    Returns:
        Aggregated counters including ``series``.
    """
    wanted = {c.upper() for c in series_codes} if series_codes else None
    totals = {
        "series": 0,
        "products": 0,
        "skus": 0,
        "attributes": 0,
        "images_created": 0,
        "images_failed": 0,
    }
    for series in load_ball_valve_series(csv_path):
        if wanted is not None and series.code not in wanted:
            continue
        stats = apply_series_enrichment(series, import_images=import_images)
        if stats["products"] == 0:
            logger.warning("Product missing for %s (%s)", series.code, series.product_slug)
            continue
        totals["series"] += 1
        for key in (
            "products",
            "skus",
            "attributes",
            "images_created",
            "images_failed",
        ):
            totals[key] += stats[key]
    return totals
