"""Canonical copy + ТТХ for Hoocon ball valves.

* Brass bodies (``8100-bv*``): valve only + RFQ kit picker.
* H81 factory kits (**H8101…H8122**): complete valve+actuator editions
  ``H8101-BV215A-24AS`` … ``H8122-BV2150-230DS``.
* H8205 LAV regulating valves: ``H8205-LAV232-24A`` … ``H8205-LAV3300ST-230M``.

Source: sibling Tilda store CSV, catalog 2026 шаровые, PDP pages.
Style: docs/tech-copy-belimo-ru.md.
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
from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.ball_valve_medium import (
    WORKING_MEDIUM_ATTR,
    WORKING_MEDIUM_BULLET,
    WORKING_MEDIUM_INLINE,
)
from catalog.etl.h81_kits import (
    FLANGED_STD_BODY_ROWS,
    H81KitSeries,
    all_h81_kit_series,
    h81_kit_edition_sku_codes,
    is_h81_kit_sku_code,
)
from catalog.etl.h8205_lav import (
    CONNECTION as LAV_CONNECTION,
)
from catalog.etl.h8205_lav import (
    FLOW_CHAR as LAV_FLOW_CHAR,
)
from catalog.etl.h8205_lav import (
    LEAKAGE as LAV_LEAKAGE,
)
from catalog.etl.h8205_lav import (
    MATERIAL_BODY as LAV_MATERIAL_BODY,
)
from catalog.etl.h8205_lav import (
    MATERIAL_PLUG as LAV_MATERIAL_PLUG,
)
from catalog.etl.h8205_lav import (
    MATERIAL_SEAL as LAV_MATERIAL_SEAL,
)
from catalog.etl.h8205_lav import (
    MATERIAL_SEAT as LAV_MATERIAL_SEAT,
)
from catalog.etl.h8205_lav import (
    MATERIAL_STEM as LAV_MATERIAL_STEM,
)
from catalog.etl.h8205_lav import (
    MEDIUM_TEMP as LAV_MEDIUM_TEMP,
)
from catalog.etl.h8205_lav import (
    PRESSURE_RATING as LAV_PRESSURE,
)
from catalog.etl.h8205_lav import (
    H8205LavSeries,
    all_h8205_series,
    h8205_edition_sku_codes,
    is_h8205_sku_code,
)
from catalog.etl.manual_pdfs import default_manuals_dir, find_manual_file
from catalog.etl.sku_variant import parse_sku_variant
from catalog.etl.tech_copy import (
    CONTROL_MODBUS,
    CONTROL_MODULATING,
    CONTROL_SIGNAL_Y_CANON,
    CONTROL_SIGNAL_Y_LABEL,
    FEEDBACK_SIGNAL_U_CANON,
    FEEDBACK_SIGNAL_U_LABEL,
    normalize_control_attribute_value,
    normalize_tech_copy,
)
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, convert_bytes_to_webp
from catalog.facets import normalize_aux_switch_value
from catalog.models import SKU, AttributeValue, Category, Product, ProductFile, ProductImage
from catalog.urls_paths import catalog_path_for_sku
from config.warranty import WARRANTY_BULLET, WARRANTY_LINE

# Compat aliases for older imports / tests.
FlangedKitSeries = H81KitSeries
FLANGED_BODY_ROWS = FLANGED_STD_BODY_ROWS
FLANGED_KIT_PREFIXES: tuple[str, ...] = ("H8103", "H8104")
FLANGED_VOLTAGES = ("24", "230")
FLANGED_CONTROL_SUFFIXES = ("A", "AS", "D", "DS")
LEGACY_FLANGED_BODY_CODES: tuple[str, ...] = tuple(row[0] for row in FLANGED_STD_BODY_ROWS)
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
_SERIES_RE = re.compile(r"\b(BV\d{3,4})\b", re.I)
# Brass editions: bv215a (optional bare body for legacy lookups).
_SKU_BODY_RE = re.compile(r"(?i)^(?:8100-)?bv(?P<num>\d{3,4})(?P<ed>[a-e])?$")
_SKU_EDITION_RE = re.compile(r"(?i)bv(\d{3})([a-e])\s*$")
_DN_RE = re.compile(r"DN\s*(\d+)", re.I)

AttrRow = tuple[str, str, str, str, str]

# Sibling assets for 2026 ball-valve catalog (photos + PDF).
_REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_IMAGES_DIR = (
    _REPO_ROOT / ".." / "hoocon" / "data" / "catalog" / "каталог 2026 шаровые - hoocon images"
).resolve()
_CATALOG_PDF_NAME = "каталог_2026_шаровые_hoocon_ver_1.05.pdf"
CATALOG_PDF_PATH = (
    find_manual_file(default_manuals_dir(_REPO_ROOT), _CATALOG_PDF_NAME)
    or (_REPO_ROOT / "_инструкции-pdf" / "RU" / _CATALOG_PDF_NAME).resolve()
)


def format_compatible_actuators(series: tuple[str, ...]) -> str:
    """Build «совместимый привод» value (drives only, no bracket)."""
    return f"{', '.join(series)} (−D/−DS/−A/−AS)"


def format_bracket(series: tuple[str, ...]) -> str:
    """Build «кронштейн»; BR-ML only when DA…FU is listed."""
    if any(_FU_SERIES_RE.search(item) for item in series):
        return "BR-M / BR-ML (для DA…FU)"
    return "BR-M"


def product_slug_for_series(series: str) -> str:
    """Return CMS product slug for a BV code (``BV220`` → ``8100-bv220``)."""
    code = (series or "").strip().casefold()
    if code.startswith("bv"):
        return f"8100-{code}"
    return f"8100-bv{code}"


def brass_sku_slug(product_slug: str, sku_code: str) -> str:
    """Stable SKU.slug under a brass DN Product (``8100-bv215-8100-bv215a``)."""
    return f"{product_slug}-{(sku_code or '').strip().lower()}"


def legacy_brass_product_slug(series: str) -> str:
    """Pre-rename Product slug (``BV220`` → ``sharovoy-kran-bv220``)."""
    code = (series or "").strip().casefold()
    if not code.startswith("bv"):
        code = f"bv{code}"
    return f"sharovoy-kran-{code}"


def brass_body_code_from_sku(sku_code: str) -> str | None:
    """Map ``8100-bv215a`` → ``BV215A`` (None when not a brass body SKU)."""
    match = _SKU_BODY_RE.fullmatch((sku_code or "").strip())
    if match is None:
        return None
    letter = (match.group("ed") or "").upper()
    return f"BV{match.group('num')}{letter}"


def body_meta_for_brass(body: str) -> tuple[str, str, str] | None:
    """Return ``(dn, kvs, ways)`` for a brass body code like ``BV215A``."""
    from catalog.etl.h81_kits import BRASS_KIT_BODIES

    body_u = (body or "").strip().upper()
    for row_body, dn, kvs, ways in BRASS_KIT_BODIES:
        if row_body == body_u:
            return dn, kvs, ways
    return None


def product_slug_for_flanged_kit(kit: str, body: str) -> str:
    """Return family Product slug for an H81 kit (``h8103``); body ignored."""
    _ = body
    from catalog.etl.h81_kits import h81_family_product_slug

    return h81_family_product_slug(kit)


def ball_valve_product_slugs() -> frozenset[str]:
    """All known ball-valve product slugs (brass bodies + H81 family cards)."""
    from catalog.etl.h81_kits import h81_family_prefixes, h81_family_product_slug

    brass = (
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
    kit_slugs = (h81_family_product_slug(p) for p in h81_family_prefixes())
    return frozenset(
        (*(product_slug_for_series(f"BV{n}") for n in brass), *kit_slugs),
    )


def is_flanged_kit_sku_code(sku_code: str) -> bool:
    """True for complete H81 / H8205 valve+actuator article codes."""
    return is_h81_kit_sku_code(sku_code) or is_h8205_sku_code(sku_code)


@dataclass(frozen=True)
class BallValveSeries:
    """One BV* parent + editions from the Tilda store export (brass bodies)."""

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
    material: str = "Латунь"
    voltage_note: str = ""
    gallery_local_files: tuple[str, ...] = ()

    @property
    def compatible_actuators(self) -> str:
        return format_compatible_actuators(self.drive_series)

    @property
    def bracket(self) -> str:
        return format_bracket(self.drive_series)

    @property
    def voltage_label(self) -> str:
        """Nominal actuator voltage from series family (BV2xx=24, BV3xx=230)."""
        if self.voltage_note:
            return self.voltage_note
        return "230 В" if self.code.upper().startswith("BV3") else "24 В"

    @property
    def is_flanged(self) -> bool:
        """Brass body cards are never flanged kits."""
        return False


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
    match = _SKU_BODY_RE.search((sku_code or "").strip())
    if not match:
        return None
    series_num = series.code.upper().removeprefix("BV")
    if match.group("num") != series_num:
        return None
    letter = (match.group("ed") or "").lower()
    if letter:
        return series.kvs_by_edition.get(letter)
    if "" in series.kvs_by_edition:
        return series.kvs_by_edition[""]
    if len(series.kvs_by_edition) == 1:
        return next(iter(series.kvs_by_edition.values()))
    return None


def edition_sku_codes(series: BallValveSeries) -> list[str]:
    """SKU codes for each brass Kvs edition (``8100-bv215a``)."""
    codes: list[str] = []
    base = series.code.lower()
    for letter in sorted(series.kvs_by_edition.keys(), key=lambda x: (x == "", x)):
        if letter:
            codes.append(f"8100-{base}{letter}")
        else:
            codes.append(f"8100-{base}")
    return codes


def flanged_kit_edition_sku_codes(kit: H81KitSeries) -> list[str]:
    """Eight electrical editions for one H81 kit product (compat alias)."""
    return h81_kit_edition_sku_codes(kit)


def flanged_kit_series() -> list[H81KitSeries]:
    """All H8101…H8122 kit products (compat name; prefer :func:`all_h81_kit_series`)."""
    return all_h81_kit_series()


def flanged_ball_valve_series() -> list[H81KitSeries]:
    """Alias of :func:`flanged_kit_series`."""
    return flanged_kit_series()


def load_all_ball_valve_series(csv_path: Path | None = None) -> list[BallValveSeries]:
    """Brass body series from the Tilda store CSV (flanged kits are separate)."""
    return load_ball_valve_series(csv_path)


def _series_description(series: BallValveSeries) -> str:
    join_label = "Соединение" if series.is_flanged else "Резьба"
    return normalize_tech_copy(
        f"""
Шаровой кран {series.ways} DN {series.dn} серии {series.code} для систем
отопления, вентиляции и кондиционирования (HVAC).

Назначение и особенности:
{WORKING_MEDIUM_BULLET}
– Рабочая температура среды: –9…+95 °C.
– {join_label}: {series.thread}.
– Материал корпуса: {series.material}.
– Вид: {series.ways}.
– Совместимый привод {series.voltage_label}: {series.compatible_actuators}.
– Кронштейн: {series.bracket}.
{WARRANTY_BULLET}

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
    join_label = "соединение" if series.is_flanged else "резьба"
    lines = [
        (
            f"Шаровой кран {series.ways} DN {series.dn} серии "
            f"{series.code} для систем отопления, вентиляции "
            "и кондиционирования (HVAC)."
        ),
        f"Пропускная способность: Kvs {kvs} м³/ч.",
        (f"{WORKING_MEDIUM_INLINE}; температура среды –9…+95 °C; {join_label} {series.thread}."),
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
        WARRANTY_LINE,
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
            WORKING_MEDIUM_ATTR,
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
        ("Материал корпуса", "material", "", series.material, ATTR_GROUP_MATERIALS),
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


def _kit_body_attrs(kit: H81KitSeries) -> tuple[AttrRow, ...]:
    """Shared valve-body ТТХ for one H81 kit product."""
    if kit.is_brass:
        join_name, join_slug = "Резьба", "thread"
    else:
        join_name, join_slug = "Соединение", "connection"
    rows: list[AttrRow] = [
        ("DN", "dn", "", kit.dn, ATTR_GROUP_VALVE),
        ("Вид крана", "ways", "", kit.ways, ATTR_GROUP_VALVE),
        (join_name, join_slug, "", kit.thread, ATTR_GROUP_VALVE),
        ("Kvs", "kvs", "м³/ч", kit.kvs, ATTR_GROUP_HYDRAULIC),
        (
            "Максимальный рабочий перепад давления",
            "diff-pressure",
            "МПа",
            kit.diff_pressure,
            ATTR_GROUP_HYDRAULIC,
        ),
        (
            "Рабочая среда",
            "medium",
            "",
            WORKING_MEDIUM_ATTR,
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
        (
            "Время срабатывания",
            "run-time",
            "",
            kit.run_time,
            ATTR_GROUP_FUNCTIONAL,
        ),
        (
            "Ручное управление",
            "manual-override",
            "",
            "есть",
            ATTR_GROUP_FUNCTIONAL,
        ),
        (
            "Степень защиты корпуса",
            "ip-rating",
            "",
            kit.family.ip_rating,
            ATTR_GROUP_OPERATING,
        ),
        (
            "Температура окружающей среды",
            "ambient-temp",
            "°C",
            "–20…+50",
            ATTR_GROUP_OPERATING,
        ),
        ("Материал корпуса", "material", "", kit.material, ATTR_GROUP_MATERIALS),
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
    ]
    if kit.height_actuator:
        rows.append(
            (
                "Высота до верхнего края привода",
                "height-actuator",
                "мм",
                kit.height_actuator,
                ATTR_GROUP_SIZE,
            ),
        )
    if kit.height_stem:
        rows.append(
            (
                "Высота до верхнего края штока",
                "height-stem",
                "мм",
                kit.height_stem,
                ATTR_GROUP_SIZE,
            ),
        )
    if kit.valve_length:
        rows.append(
            (
                "Длина крана",
                "valve-length",
                "мм",
                kit.valve_length,
                ATTR_GROUP_SIZE,
            ),
        )
    if kit.valve_od:
        rows.append(
            (
                "Внешний диаметр крана",
                "valve-od",
                "мм",
                kit.valve_od,
                ATTR_GROUP_SIZE,
            ),
        )
    return tuple(rows)


def _lav_series_description(series: H8205LavSeries) -> str:
    """Product-level description for one H8205 LAV body card."""
    return normalize_tech_copy(
        f"""
Электрический регулирующий клапан {series.ways} DN {series.dn} серии H8205
(корпус {series.body}) для систем автоматического управления HVAC и
смежных отраслей. Изменяет степень открытия по сигналу управления,
регулируя расход среды (температура, уровень, давление).

Назначение и особенности:
{WORKING_MEDIUM_BULLET}
– Рабочая температура среды: {LAV_MEDIUM_TEMP}.
– Номинальное давление: {LAV_PRESSURE}.
– Соединение: {LAV_CONNECTION}.
– Материал корпуса: {LAV_MATERIAL_BODY}.
– Вид: {series.ways}.
– Расходная характеристика: {LAV_FLOW_CHAR}.
– Утечка: {LAV_LEAKAGE}.
{WARRANTY_BULLET}

Область применения:
– Системы отопления, вентиляции и кондиционирования (HVAC).
– Нефтехимическая, металлургическая, электроэнергетическая отрасли.
– Природоохранные и другие промышленные АСУ ТП.
""".strip(),
    )


def _lav_sku_description(series: H8205LavSeries, sku_code: str) -> str:
    """Edition description with voltage / control / S / T from the SKU code."""
    variant = parse_sku_variant(sku_code)
    if variant.voltage == "230":
        volt_label = "AC 100…240 В"
    else:
        volt_label = "AC/DC 24 В"
    if variant.control == "modulating":
        control_label = "аналоговое (пропорциональное)"
    elif variant.control == "modbus":
        control_label = "Modbus RS-485"
    else:
        control_label = "дискретное (открыто/закрыто)"
    extras: list[str] = []
    if variant.aux_switch:
        extras.append("вспомогательный переключатель")
    if variant.fault_alarm:
        extras.append("аварийный сигнал")
    extra_label = f" ({', '.join(extras)})" if extras else ""
    lines = [
        f"Исполнение {sku_code}: питание {volt_label}, управление: {control_label}{extra_label}.",
        "",
        "Область применения:",
        "– Системы отопления, вентиляции и кондиционирования (HVAC).",
        "– Промышленные АСУ ТП.",
        "",
        WARRANTY_LINE,
    ]
    return normalize_tech_copy("\n".join(lines))


def _lav_body_attrs(series: H8205LavSeries) -> tuple[AttrRow, ...]:
    """Shared ТТХ rows for one LAV body (all electrical editions)."""
    rows: list[AttrRow] = [
        ("DN", "dn", "", series.dn, ATTR_GROUP_VALVE),
        ("Вид", "ways", "", series.ways, ATTR_GROUP_VALVE),
        ("Номинальное давление", "pressure-rating", "", LAV_PRESSURE, ATTR_GROUP_OPERATING),
        ("Соединение", "connection", "", LAV_CONNECTION, ATTR_GROUP_VALVE),
        ("Рабочая среда", "medium", "", WORKING_MEDIUM_ATTR, ATTR_GROUP_OPERATING),
        ("Температура среды", "media-temp", "", LAV_MEDIUM_TEMP, ATTR_GROUP_OPERATING),
        ("Утечка", "leakage", "", LAV_LEAKAGE, ATTR_GROUP_HYDRAULIC),
        ("Расходная характеристика", "flow-characteristic", "", LAV_FLOW_CHAR, ATTR_GROUP_HYDRAULIC),
        ("Материал корпуса", "material", "", LAV_MATERIAL_BODY, ATTR_GROUP_MATERIALS),
        ("Материал штока", "material-stem", "", LAV_MATERIAL_STEM, ATTR_GROUP_MATERIALS),
        ("Материал затвора", "material-plug", "", LAV_MATERIAL_PLUG, ATTR_GROUP_MATERIALS),
        ("Материал седла", "material-seat", "", LAV_MATERIAL_SEAT, ATTR_GROUP_MATERIALS),
        ("Уплотнительное кольцо", "material-seal", "", LAV_MATERIAL_SEAL, ATTR_GROUP_MATERIALS),
        ("Строительная длина C", "face-to-face", "мм", series.face_to_face_c, ATTR_GROUP_SIZE),
        ("Длина L", "valve-length", "мм", series.length_l, ATTR_GROUP_SIZE),
        ("Высота H", "height", "мм", series.height_h, ATTR_GROUP_SIZE),
        ("Фланец PN16 ØD", "flange-od-pn16", "мм", series.pn16_od, ATTR_GROUP_SIZE),
        ("Фланец PN16 D1", "flange-pcd-pn16", "мм", series.pn16_pcd, ATTR_GROUP_SIZE),
        ("Болты PN16", "flange-bolts-pn16", "", series.pn16_bolts, ATTR_GROUP_SIZE),
        ("Фланец PN25 ØD", "flange-od-pn25", "мм", series.pn25_od, ATTR_GROUP_SIZE),
        ("Фланец PN25 D1", "flange-pcd-pn25", "мм", series.pn25_pcd, ATTR_GROUP_SIZE),
        ("Болты PN25", "flange-bolts-pn25", "", series.pn25_bolts, ATTR_GROUP_SIZE),
        ("Высота фланца f", "flange-face", "мм", series.flange_face_f, ATTR_GROUP_SIZE),
    ]
    if series.height_h1:
        rows.append(
            ("Высота H1", "height-h1", "мм", series.height_h1, ATTR_GROUP_SIZE),
        )
    if series.height_h2:
        rows.append(
            ("Высота H2", "height-h2", "мм", series.height_h2, ATTR_GROUP_SIZE),
        )
    return tuple(rows)


def _apply_lav_variant_attrs(sku: SKU) -> int:
    """Write voltage / control / aux / fault from an H8205 edition code."""
    variant = parse_sku_variant(sku.sku_code)
    written = 0
    if variant.voltage == "24":
        _set_attr(
            sku,
            "Номинальное напряжение",
            "voltage",
            "",
            "AC/DC 24 В, 50/60 Гц",
        )
        written += 1
    elif variant.voltage == "230":
        _set_attr(
            sku,
            "Номинальное напряжение",
            "voltage",
            "",
            "AC 100…240 В, 50/60 Гц",
        )
        written += 1
    if variant.control == "modulating":
        _set_attr(sku, "Управление", "control", "", CONTROL_MODULATING)
        _set_attr(
            sku,
            CONTROL_SIGNAL_Y_LABEL,
            "control-signal-y",
            "",
            CONTROL_SIGNAL_Y_CANON,
        )
        _set_attr(
            sku,
            FEEDBACK_SIGNAL_U_LABEL,
            "feedback-signal-u",
            "",
            FEEDBACK_SIGNAL_U_CANON,
        )
        written += 3
    elif variant.control == "modbus":
        _set_attr(sku, "Управление", "control", "", CONTROL_MODBUS)
        written += 1
    elif variant.control == "on_off":
        _set_attr(
            sku,
            "Управление",
            "control",
            "",
            normalize_control_attribute_value("открыто/закрыто", sku_code=sku.sku_code),
        )
        written += 1
    if variant.aux_switch is True:
        aux_val = normalize_aux_switch_value("SPDT-2", sku_code=sku.sku_code)
        _set_attr(
            sku,
            "Вспомогательный переключатель",
            "aux-switch",
            "",
            aux_val,
        )
        written += 1
    elif variant.aux_switch is False:
        _set_attr(
            sku,
            "Вспомогательный переключатель",
            "aux-switch",
            "",
            normalize_aux_switch_value("Нет", sku_code=sku.sku_code),
        )
        written += 1
    if variant.fault_alarm is True:
        _set_attr(sku, "Аварийный сигнал", "fault-alarm", "", "есть")
        written += 1
    elif variant.fault_alarm is False:
        _set_attr(sku, "Аварийный сигнал", "fault-alarm", "", "нет")
        written += 1
    return written


def ensure_h8205_lav_series(series: H8205LavSeries) -> dict[str, int]:
    """Create missing Product + 24 electrical SKUs for one H8205 LAV card."""
    from catalog.series_categories import kits_category_slug

    slug = kits_category_slug()
    category = Category.objects.filter(slug=slug).first()
    if category is None:
        category = Category.objects.create(slug=slug, name="Комплекты")
        logger.info("Created category %s", slug)

    products_created = 0
    skus_created = 0
    product = Product.objects.filter(slug=series.product_slug).first()
    if product is None:
        product = Product.objects.create(
            category=category,
            name=series.product_name[:200],
            slug=series.product_slug,
            description=_lav_series_description(series),
        )
        products_created = 1
    else:
        product.category = category
        product.save(update_fields=["category"])

    for sku_code in h8205_edition_sku_codes(series):
        if SKU.objects.filter(sku_code__iexact=sku_code).exists():
            continue
        slug_sku = f"{series.product_slug}-{sku_code.lower()}"
        if SKU.objects.filter(slug=slug_sku).exists():
            slug_sku = f"{slug_sku}-{SKU.objects.count()}"
        SKU.objects.create(
            product=product,
            name=series.product_name[:300],
            slug=slug_sku[:300],
            sku_code=sku_code,
            description="",
            is_published=True,
        )
        skus_created += 1
    return {"products_created": products_created, "skus_created": skus_created}


def apply_h8205_lav_enrichment(
    series: H8205LavSeries,
    *,
    attach_pdf: bool = True,
) -> dict[str, int]:
    """Seed + rewrite one H8205 LAV product (24 electrical editions)."""
    ensure_h8205_lav_series(series)
    product = Product.objects.filter(slug=series.product_slug).first()
    if product is None:
        return {
            "products": 0,
            "skus": 0,
            "attributes": 0,
            "images_created": 0,
            "images_failed": 0,
            "pdf_attached": 0,
        }

    product.name = series.product_name[:200]
    product.description = _lav_series_description(series)
    product.specs_text = ""
    product.save(update_fields=["name", "description", "specs_text"])

    wanted = {c.upper() for c in h8205_edition_sku_codes(series)}
    skus = [
        sku
        for sku in SKU.objects.filter(product=product).order_by("sku_code")
        if (sku.sku_code or "").upper() in wanted
    ]
    attrs = 0
    pdf_attached = 0
    body_attrs = _lav_body_attrs(series)

    for sku in skus:
        sku.name = series.product_name[:300]
        sku.description = _lav_sku_description(series, sku.sku_code)
        sku.is_published = True
        sku.specs_text = ""
        sku.save(update_fields=["name", "description", "specs_text", "is_published"])

        AttributeValue.objects.filter(sku=sku).delete()
        for name, slug, unit, value, _group in body_attrs:
            if not value:
                continue
            _set_attr(sku, name, slug, unit, value)
            attrs += 1
        attrs += _apply_lav_variant_attrs(sku)

        if attach_pdf and attach_catalog_pdf(sku):
            pdf_attached += 1

    return {
        "products": 1,
        "skus": len(skus),
        "attributes": attrs,
        "images_created": 0,
        "images_failed": 0,
        "pdf_attached": pdf_attached,
    }


def _lav_matches_filter(series: H8205LavSeries, wanted: set[str]) -> bool:
    """Match ``--series H8205`` / ``LAV280`` / ``H8205-LAV232``."""
    code = series.code.upper()
    body = series.body.upper()
    return (
        code in wanted
        or body in wanted
        or "H8205" in wanted
        or f"H8205-{body}" in wanted
        or f"BV{series.dn}" in wanted
    )


def _apply_kit_variant_attrs(sku: SKU, kit: H81KitSeries) -> int:
    """Write voltage / control / aux / power from the edition sku_code."""
    variant = parse_sku_variant(sku.sku_code)
    written = 0
    if variant.voltage == "24":
        _set_attr(
            sku,
            "Номинальное напряжение",
            "voltage",
            "",
            "AC/DC 24 В, 50/60 Гц",
        )
        written += 1
    elif variant.voltage == "230":
        _set_attr(
            sku,
            "Номинальное напряжение",
            "voltage",
            "",
            "AC 100…240 В, 50/60 Гц",
        )
        written += 1
    if variant.voltage:
        _set_attr(
            sku,
            "Потребляемая мощность",
            "power-consumption",
            "",
            kit.power_consumption(variant.voltage),
        )
        written += 1
    if variant.control == "modulating":
        _set_attr(sku, "Управление", "control", "", CONTROL_MODULATING)
        _set_attr(
            sku,
            CONTROL_SIGNAL_Y_LABEL,
            "control-signal-y",
            "",
            CONTROL_SIGNAL_Y_CANON,
        )
        _set_attr(
            sku,
            FEEDBACK_SIGNAL_U_LABEL,
            "feedback-signal-u",
            "",
            FEEDBACK_SIGNAL_U_CANON,
        )
        written += 3
    elif variant.control == "on_off":
        _set_attr(
            sku,
            "Управление",
            "control",
            "",
            normalize_control_attribute_value("2-/3-позиционное"),
        )
        written += 1
    if variant.aux_switch is True:
        # Catalog «Подключение…»: два концевых выключателя (a + b) → SPDT-2.
        aux_val = normalize_aux_switch_value("SPDT-2", sku_code=sku.sku_code)
        _set_attr(
            sku,
            "Вспомогательный переключатель",
            "aux-switch",
            "",
            aux_val,
        )
        written += 1
    return written


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


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
        updated = ProductImage.objects.filter(sku=sku, source_url=url).update(
            sort_order=sort_order,
            is_published=True,
        )
        if updated:
            existing += 1
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


def ensure_ball_valve_series(series: BallValveSeries) -> dict[str, int]:
    """Create missing Product + SKU editions for one brass BV* series.

    Returns:
        Counters ``products_created`` / ``skus_created``.
    """
    category = Category.objects.filter(slug="sharovye-krany").first()
    if category is None:
        logger.error("Category sharovye-krany missing — cannot seed %s", series.code)
        return {"products_created": 0, "skus_created": 0}

    products_created = 0
    skus_created = 0
    product = Product.objects.filter(slug=series.product_slug).first()
    if product is None:
        product = Product.objects.create(
            category=category,
            name=series.product_name[:200],
            slug=series.product_slug,
            description=_series_description(series),
        )
        products_created = 1
    else:
        product.category = category
        product.save(update_fields=["category"])

    for sku_code in edition_sku_codes(series):
        existing = SKU.objects.filter(sku_code__iexact=sku_code).first()
        if existing is not None:
            if existing.product_id != product.pk:
                existing.product = product
                existing.save(update_fields=["product"])
            continue
        slug = brass_sku_slug(series.product_slug, sku_code)
        if SKU.objects.filter(slug=slug).exists():
            slug = f"{slug}-{SKU.objects.count()}"
        SKU.objects.create(
            product=product,
            name=series.product_name[:300],
            slug=slug[:300],
            sku_code=sku_code,
            description="",
            is_published=True,
        )
        skus_created += 1
    return {"products_created": products_created, "skus_created": skus_created}


def _kit_series_description(kit: H81KitSeries) -> str:
    join_label = "Резьба" if kit.is_brass else "Соединение"
    return normalize_tech_copy(
        f"""
Электрический шаровой кран {kit.ways} DN {kit.dn} серии {kit.kit}
({kit.speed_label} серия) для систем отопления, вентиляции и
кондиционирования (HVAC). Комплект: корпус {kit.body} + электропривод.

Назначение и особенности:
{WORKING_MEDIUM_BULLET}
– Рабочая температура среды: –9…+95 °C.
– {join_label}: {kit.thread}.
– Материал корпуса: {kit.material}.
– Вид: {kit.ways}.
– Время срабатывания: {kit.run_time}.
– Степень защиты привода: {kit.family.ip_rating}.
– Ручное управление: есть.
{WARRANTY_BULLET}

Область применения:
– Системы обработки воздуха.
– VAV-системы вентиляции и осушения (фанкойлы).
– Вентиляционные установки.
– Воздухоподогреватели.
– Крышные кондиционеры.
– Бойлерные системы (чиллеры).
""".strip(),
    )


def _kit_sku_description(kit: H81KitSeries, sku_code: str) -> str:
    variant = parse_sku_variant(sku_code)
    control_label = "плавное (аналоговое)" if variant.control == "modulating" else "открыто/закрыто"
    aux_label = (
        "с двумя вспомогательными переключателями" if variant.aux_switch else "без вспомогательных переключателей"
    )
    volt = variant.voltage or "?"
    join_word = "резьба" if kit.is_brass else "соединение"
    lines = [
        (
            f"Электрический шаровой кран {kit.ways} DN {kit.dn} "
            f"{kit.kit}-{kit.body} ({kit.speed_label} серия) для систем "
            "отопления, вентиляции и кондиционирования (HVAC)."
        ),
        f"Пропускная способность: Kvs {kit.kvs} м³/ч.",
        (f"{WORKING_MEDIUM_INLINE}; температура среды –9…+95 °C; {join_word} {kit.thread}."),
        f"Номинальное напряжение: {volt} В.",
        f"Управление: {control_label} ({aux_label}).",
        f"Время срабатывания: {kit.run_time}.",
        "",
        "Область применения:",
        "– Системы обработки воздуха.",
        "– VAV-системы вентиляции и осушения (фанкойлы).",
        "– Вентиляционные установки.",
        "– Воздухоподогреватели.",
        "– Крышные кондиционеры.",
        "– Бойлерные системы (чиллеры).",
        "",
        WARRANTY_LINE,
    ]
    return normalize_tech_copy("\n".join(lines))


def ensure_flanged_kit_series(kit: FlangedKitSeries) -> dict[str, int]:
    """Create missing family Product + 8 electrical SKUs for one body row."""
    from catalog.etl.h81_kits import h81_sku_slug
    from catalog.series_categories import kits_category_slug

    slug = kits_category_slug()
    category = Category.objects.filter(slug=slug).first()
    if category is None:
        category = Category.objects.create(slug=slug, name="Комплекты")
        logger.info("Created category %s", slug)

    products_created = 0
    skus_created = 0
    product = Product.objects.filter(slug=kit.product_slug).first()
    if product is None:
        product = Product.objects.create(
            category=category,
            name=kit.product_name[:200],
            slug=kit.product_slug,
            description=_kit_family_description(kit),
        )
        products_created = 1
    else:
        product.category = category
        product.save(update_fields=["category"])

    for sku_code in flanged_kit_edition_sku_codes(kit):
        existing = SKU.objects.filter(sku_code__iexact=sku_code).first()
        if existing is not None:
            if existing.product_id != product.pk:
                existing.product = product
                existing.save(update_fields=["product"])
            continue
        slug_sku = h81_sku_slug(kit.product_slug, sku_code)
        if SKU.objects.filter(slug=slug_sku).exists():
            slug_sku = f"{slug_sku}-{SKU.objects.count()}"
        SKU.objects.create(
            product=product,
            name=kit.sku_display_name[:300],
            slug=slug_sku[:300],
            sku_code=sku_code,
            description="",
            is_published=True,
        )
        skus_created += 1
    return {"products_created": products_created, "skus_created": skus_created}


def _kit_family_description(kit: H81KitSeries) -> str:
    """Shared Product description for one H81xx series card."""
    kind = "латунный резьбовой" if kit.is_brass else "фланцевый ВЧШГ"
    return normalize_tech_copy(
        f"""
Электрические шаровые краны серии {kit.kit} ({kit.speed_label} серия,
{kind}) — заводские комплекты корпус + электропривод для систем HVAC.

Назначение и особенности:
{WORKING_MEDIUM_BULLET}
– Рабочая температура среды: –9…+95 °C.
– Материал корпуса: {kit.material}.
– Время срабатывания: {kit.run_time} (зависит от DN у части серий).
– Степень защиты привода: {kit.family.ip_rating}.
– Ручное управление: есть.
{WARRANTY_BULLET}

Область применения:
– Системы обработки воздуха.
– VAV-системы вентиляции и осушения (фанкойлы).
– Вентиляционные установки.
– Воздухоподогреватели.
– Крышные кондиционеры.
– Бойлерные системы (чиллеры).
""".strip(),
    )


def attach_local_gallery_images(
    sku: SKU,
    filenames: tuple[str, ...],
    *,
    alt_prefix: str,
    images_dir: Path | None = None,
    quality: int = DEFAULT_WEBP_QUALITY,
) -> dict[str, int]:
    """Attach local catalog JPEGs as WebP gallery (idempotent by source_url)."""
    root = (images_dir or CATALOG_IMAGES_DIR).resolve()
    created = 0
    existing = 0
    failed = 0
    for sort_order, name in enumerate(filenames):
        path = root / name
        source_url = f"https://hoocon.ru/.local-catalog/{name}"
        updated = ProductImage.objects.filter(sku=sku, source_url=source_url).update(
            sort_order=sort_order,
            is_published=True,
        )
        if updated:
            existing += 1
            continue
        if not path.is_file():
            failed += 1
            logger.warning("Local gallery missing %s for %s", path, sku.sku_code)
            continue
        try:
            raw = path.read_bytes()
            webp = convert_bytes_to_webp(raw, quality=quality)
            filename = f"{sku.sku_code.lower()}-local-{sort_order}.webp"
            with transaction.atomic():
                img = ProductImage(
                    sku=sku,
                    alt=f"{alt_prefix} — фото {sort_order + 1}"[:300],
                    source_url=source_url,
                    sort_order=sort_order,
                    is_published=True,
                )
                img.image.save(filename, ContentFile(webp), save=False)
                img.full_clean()
                img.save()
            created += 1
        except (OSError, ValueError, ValidationError) as exc:
            failed += 1
            logger.warning("Local gallery fail %s %s: %s", sku.sku_code, name, exc)
    return {"created": created, "existing": existing, "failed": failed}


def attach_catalog_pdf(sku: SKU, *, pdf_path: Path | None = None) -> bool:
    """Attach the 2026 ball-valve catalog PDF once per SKU (file_type=catalog).

    Skips silently when the PDF is missing or larger than the ProductFile
    upload limit (full print catalog is ~70 MiB).
    """
    from catalog.validators import MAX_PRODUCT_FILE_SIZE_BYTES

    path = (pdf_path or CATALOG_PDF_PATH).resolve()
    title = "Каталог шаровых кранов Hoocon 2026"
    if ProductFile.objects.filter(
        sku=sku,
        title=title,
        file_type=ProductFile.FileType.CATALOG,
    ).exists():
        return False
    if not path.is_file():
        logger.warning("Catalog PDF missing: %s", path)
        return False
    size = path.stat().st_size
    if size > MAX_PRODUCT_FILE_SIZE_BYTES:
        logger.warning(
            "Catalog PDF too large for ProductFile (%s > %s) — skip attach",
            size,
            MAX_PRODUCT_FILE_SIZE_BYTES,
        )
        return False
    with path.open("rb") as fh:
        data = fh.read()
    doc = ProductFile(
        sku=sku,
        title=title,
        file_type=ProductFile.FileType.CATALOG,
        is_published=True,
        sort_order=50,
    )
    doc.file.save("katalog-sharovye-hoocon-2026.pdf", ContentFile(data), save=False)
    doc.full_clean()
    doc.save()
    return True


def apply_series_enrichment(
    series: BallValveSeries,
    *,
    import_images: bool = True,
    attach_pdf: bool = True,
) -> dict[str, int]:
    """Rewrite one BV* product/SKUs: copy, ТТХ cards, gallery."""
    ensure_ball_valve_series(series)
    product = Product.objects.filter(slug=series.product_slug).first()
    if product is None:
        return {
            "products": 0,
            "skus": 0,
            "attributes": 0,
            "images_created": 0,
            "images_failed": 0,
            "pdf_attached": 0,
        }

    product.name = series.product_name[:200]
    product.description = _series_description(series)
    product.specs_text = ""
    product.save(update_fields=["name", "description", "specs_text"])

    skus = list(SKU.objects.filter(product=product).order_by("sku_code"))
    attrs = 0
    images_created = 0
    images_failed = 0
    pdf_attached = 0
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
        if import_images and series.gallery_local_files:
            local_stats = attach_local_gallery_images(
                sku,
                series.gallery_local_files,
                alt_prefix=series.product_name,
            )
            images_created += local_stats["created"]
            images_failed += local_stats["failed"]
        if attach_pdf and attach_catalog_pdf(sku):
            pdf_attached += 1

    return {
        "products": 1,
        "skus": len(skus),
        "attributes": attrs,
        "images_created": images_created,
        "images_failed": images_failed,
        "pdf_attached": pdf_attached,
    }


def apply_flanged_kit_enrichment(
    kit: FlangedKitSeries,
    *,
    import_images: bool = True,
    attach_pdf: bool = True,
) -> dict[str, int]:
    """Seed + rewrite one H81 body row (8 electrical editions on family Product).

    Gallery photo/dims are attached once via :func:`apply_h81_catalog_media`
    (``import_images`` kept for API compatibility; ignored here).
    """
    _ = import_images
    ensure_flanged_kit_series(kit)
    product = Product.objects.filter(slug=kit.product_slug).first()
    if product is None:
        return {
            "products": 0,
            "skus": 0,
            "attributes": 0,
            "images_created": 0,
            "images_failed": 0,
            "pdf_attached": 0,
        }

    product.name = kit.product_name[:200]
    product.description = _kit_family_description(kit)
    product.specs_text = ""
    product.save(update_fields=["name", "description", "specs_text"])

    wanted = {c.upper() for c in flanged_kit_edition_sku_codes(kit)}
    skus = [
        sku
        for sku in SKU.objects.filter(product=product).order_by("sku_code")
        if (sku.sku_code or "").upper() in wanted
    ]
    attrs = 0
    images_created = 0
    images_failed = 0
    pdf_attached = 0
    body_attrs = _kit_body_attrs(kit)

    for sku in skus:
        sku.name = kit.sku_display_name[:300]
        sku.description = _kit_sku_description(kit, sku.sku_code)
        sku.is_published = True
        sku.specs_text = ""
        sku.save(update_fields=["name", "description", "specs_text", "is_published"])

        AttributeValue.objects.filter(sku=sku).delete()
        for name, slug, unit, value, _group in body_attrs:
            if not value:
                continue
            _set_attr(sku, name, slug, unit, value)
            attrs += 1
        attrs += _apply_kit_variant_attrs(sku, kit)

        if attach_pdf and attach_catalog_pdf(sku):
            pdf_attached += 1

    return {
        "products": 1,
        "skus": len(skus),
        "attributes": attrs,
        "images_created": images_created,
        "images_failed": images_failed,
        "pdf_attached": pdf_attached,
    }


def _kit_matches_filter(kit: H81KitSeries, wanted: set[str]) -> bool:
    """Match ``--series BV265`` / ``H8103`` / ``H8101-BV215A`` / ``BV215``."""
    code = kit.code.upper()
    body = kit.body.upper()
    prefix = kit.kit.upper()
    body_core = re.sub(r"[A-E]$", "", body)
    return code in wanted or body in wanted or body_core in wanted or prefix in wanted or f"BV{kit.dn}" in wanted


def ensure_h81_kit_category_redirects(*, dry_run: bool = False) -> int:
    """301 ``/catalog/sharovye-krany/<kit-sku>`` → ``/catalog/komplekty/<kit-sku>``.

    Covers H8101…H8122 and H8205 when present. Idempotent by ``from_path``.

    Args:
        dry_run: Count without writing Redirect rows.

    Returns:
        Number of redirects created (or that would be created).
    """
    from catalog.series_categories import ball_valves_category_slug, kits_category_slug
    from catalog.urls_paths import catalog_sku_path
    from redirects.models import Redirect
    from redirects.pathutils import normalize_path

    old_cat = ball_valves_category_slug()
    new_cat = kits_category_slug()
    kit_qs = SKU.objects.filter(
        sku_code__iregex=r"(?i)^h81(?:01|02|03|04|05|06|07|08|21|22)-bv",
    ).only("slug")
    lav_qs = SKU.objects.filter(sku_code__istartswith="H8205").only("slug")
    created = 0
    for sku in list(kit_qs) + list(lav_qs):
        slug = (sku.slug or "").strip()
        if not slug:
            continue
        from_path = normalize_path(catalog_sku_path(old_cat, slug))
        to_path = normalize_path(catalog_sku_path(new_cat, slug))
        if not from_path or not to_path or from_path == to_path:
            continue
        if Redirect.objects.filter(from_path=from_path).exists():
            continue
        if dry_run:
            created += 1
            continue
        _, was_created = Redirect.objects.update_or_create(
            from_path=from_path,
            defaults={
                "to_path": to_path,
                "status_code": 301,
                "is_active": True,
            },
        )
        if was_created:
            created += 1
    return created


def merge_brass_bv_onto_dn_products(
    *,
    series_codes: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Move brass SKUs onto ``8100-bv*`` DN Products; 301 from legacy slugs.

    Legacy cards used ``sharovoy-kran-bv215``; target is ``8100-bv215`` with
    SKU slug ``8100-bv215-8100-bv215a`` (Kvs editions as siblings).

    Args:
        series_codes: Optional filter like ``("BV215", "BV220")``.
        dry_run: Count without writing.

    Returns:
        Counters ``skus_moved``, ``slugs_renamed``, ``redirects``,
        ``products_retired``.
    """
    from catalog.urls_paths import catalog_sku_path
    from redirects.models import Redirect
    from redirects.pathutils import normalize_path

    wanted = {c.upper() for c in series_codes} if series_codes else None
    category = Category.objects.filter(slug="sharovye-krany").first()
    stats = {
        "skus_moved": 0,
        "slugs_renamed": 0,
        "redirects": 0,
        "products_retired": 0,
    }
    if category is None and not dry_run:
        logger.error("Category sharovye-krany missing — cannot merge brass DN cards")
        return stats

    cat_slug = "sharovye-krany"
    for series in load_all_ball_valve_series():
        if wanted is not None and series.code not in wanted:
            continue
        product_slug = series.product_slug
        legacy_slug = legacy_brass_product_slug(series.code)
        if dry_run:
            product = Product.objects.filter(slug=product_slug).first()
        else:
            assert category is not None
            product, _created = Product.objects.get_or_create(
                slug=product_slug,
                defaults={
                    "category": category,
                    "name": series.product_name[:200],
                    "description": _series_description(series),
                },
            )
            if product.category_id != category.pk:
                product.category = category
                product.save(update_fields=["category"])
            product.name = series.product_name[:200]
            product.description = _series_description(series)
            product.save(update_fields=["name", "description"])

        sku_by_pk: dict[int, SKU] = {}
        for code in edition_sku_codes(series):
            for row in SKU.objects.filter(sku_code__iexact=code).select_related(
                "product",
                "product__category",
            ):
                sku_by_pk[row.pk] = row
        legacy_product = Product.objects.filter(slug=legacy_slug).first()
        if legacy_product is not None:
            for row in SKU.objects.filter(product_id=legacy_product.pk).select_related(
                "product",
                "product__category",
            ):
                sku_by_pk[row.pk] = row

        for sku in sku_by_pk.values():
            old_slug = (sku.slug or "").strip()
            new_slug = brass_sku_slug(product_slug, sku.sku_code or "")
            old_cat = ""
            if sku.product_id and sku.product.category_id:
                old_cat = sku.product.category.slug or ""

            if dry_run:
                if product is None or sku.product_id != getattr(product, "pk", None):
                    stats["skus_moved"] += 1
                if old_slug != new_slug:
                    stats["slugs_renamed"] += 1
                if old_slug and old_cat:
                    old_path = normalize_path(catalog_sku_path(old_cat, old_slug))
                    new_path = normalize_path(catalog_sku_path(cat_slug, new_slug))
                    if old_path and new_path and old_path != new_path:
                        stats["redirects"] += 1
                continue

            assert product is not None
            changed: list[str] = []
            if sku.product_id != product.pk:
                sku.product = product
                changed.append("product")
                stats["skus_moved"] += 1
            if old_slug != new_slug:
                if SKU.objects.filter(slug=new_slug).exclude(pk=sku.pk).exists():
                    new_slug = f"{new_slug}-{sku.pk}"
                sku.slug = new_slug[:300]
                changed.append("slug")
                stats["slugs_renamed"] += 1
            if changed:
                sku.save(update_fields=changed)

            if old_slug and old_cat:
                old_path = normalize_path(catalog_sku_path(old_cat, old_slug))
                to_path = normalize_path(catalog_sku_path(cat_slug, sku.slug))
                if old_path and to_path and old_path != to_path:
                    _, was_created = Redirect.objects.update_or_create(
                        from_path=old_path,
                        defaults={
                            "to_path": to_path,
                            "status_code": 301,
                            "is_active": True,
                        },
                    )
                    if was_created:
                        stats["redirects"] += 1

        if legacy_product is not None and not legacy_product.skus.exists():
            if dry_run:
                stats["products_retired"] += 1
            else:
                legacy_product.delete()
                stats["products_retired"] += 1

    return stats


def merge_h81_kits_onto_family_products(
    *,
    prefixes: tuple[str, ...] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Move H81 SKUs onto one Product per series; rename slugs; 301 old URLs.

    Legacy body cards used ``sharovoy-kran-h8101-bv215a``; target is ``h8101``
    with SKU slug ``h8101-h8101-bv215a-24as``.

    Args:
        prefixes: Optional filter like ``("H8101", "H8121")``.
        dry_run: Count without writing.

    Returns:
        Counters ``skus_moved``, ``slugs_renamed``, ``redirects``,
        ``products_retired``.
    """
    from catalog.etl.h81_kits import (
        KIT_FAMILIES,
        h81_family_prefixes,
        h81_family_product_name,
        h81_family_product_slug,
        h81_sku_slug,
        parse_h81_kit_parts,
    )
    from catalog.series_categories import kits_category_slug
    from catalog.urls_paths import catalog_sku_path
    from redirects.models import Redirect
    from redirects.pathutils import normalize_path

    wanted = {p.upper() for p in prefixes} if prefixes else None
    cat_slug = kits_category_slug()
    category = Category.objects.filter(slug=cat_slug).first()
    if category is None and not dry_run:
        category = Category.objects.create(slug=cat_slug, name="Комплекты")

    stats = {
        "skus_moved": 0,
        "slugs_renamed": 0,
        "redirects": 0,
        "products_retired": 0,
    }
    family_by_prefix = {f.prefix: f for f in KIT_FAMILIES}

    for prefix in h81_family_prefixes():
        if wanted is not None and prefix not in wanted:
            continue
        family = family_by_prefix[prefix]
        product_slug = h81_family_product_slug(prefix)
        if dry_run:
            product = Product.objects.filter(slug=product_slug).first()
        else:
            if category is None:
                category = Category.objects.create(slug=cat_slug, name="Комплекты")
            product, _created = Product.objects.get_or_create(
                slug=product_slug,
                defaults={
                    "category": category,
                    "name": h81_family_product_name(family)[:200],
                    "description": "",
                },
            )
            if product.category_id != category.pk:
                product.category = category
                product.save(update_fields=["category"])
            product.name = h81_family_product_name(family)[:200]
            product.save(update_fields=["name"])

        skus = list(
            SKU.objects.filter(sku_code__istartswith=f"{prefix}-").select_related(
                "product",
                "product__category",
            ),
        )
        for sku in skus:
            parts = parse_h81_kit_parts(sku.sku_code or "")
            if parts is None:
                continue
            old_slug = (sku.slug or "").strip()
            new_slug = h81_sku_slug(product_slug, sku.sku_code)
            old_cat = ""
            if sku.product_id and sku.product.category_id:
                old_cat = sku.product.category.slug or ""
            new_path = normalize_path(catalog_sku_path(cat_slug, new_slug))

            if dry_run:
                if product is None or sku.product_id != getattr(product, "pk", None):
                    stats["skus_moved"] += 1
                if old_slug != new_slug:
                    stats["slugs_renamed"] += 1
                if old_slug and old_cat:
                    old_path = normalize_path(catalog_sku_path(old_cat, old_slug))
                    if old_path and new_path and old_path != new_path:
                        stats["redirects"] += 1
                continue

            assert product is not None
            changed: list[str] = []
            if sku.product_id != product.pk:
                sku.product = product
                changed.append("product")
                stats["skus_moved"] += 1
            if old_slug != new_slug:
                # Avoid unique collisions when another row already has new_slug.
                if SKU.objects.filter(slug=new_slug).exclude(pk=sku.pk).exists():
                    new_slug = f"{new_slug}-{sku.pk}"
                sku.slug = new_slug[:300]
                changed.append("slug")
                stats["slugs_renamed"] += 1
            if changed:
                sku.save(update_fields=changed)

            if old_slug and old_cat:
                old_path = normalize_path(catalog_sku_path(old_cat, old_slug))
                to_path = normalize_path(catalog_sku_path(cat_slug, sku.slug))
                if old_path and to_path and old_path != to_path:
                    _, was_created = Redirect.objects.update_or_create(
                        from_path=old_path,
                        defaults={
                            "to_path": to_path,
                            "status_code": 301,
                            "is_active": True,
                        },
                    )
                    if was_created:
                        stats["redirects"] += 1
                # Also redirect old komplekty path if slug changed under same cat.
                if old_cat == cat_slug and old_slug != sku.slug:
                    pass  # already handled via old_path above

        # Retire empty legacy body Products for this prefix.
        legacy = Product.objects.filter(
            slug__startswith=f"sharovoy-kran-{prefix.casefold()}-",
        )
        for legacy_product in legacy:
            if legacy_product.skus.exists():
                continue
            if dry_run:
                stats["products_retired"] += 1
                continue
            legacy_product.delete()
            stats["products_retired"] += 1

    return stats


def retire_legacy_flanged_body_skus() -> dict[str, int]:
    """Unpublish mistaken ``8100-bv265…2150`` bodies and add 301 to H8103-*-24A.

    Returns:
        Counters ``skus_unpublished`` / ``redirects``.
    """
    from redirects.models import Redirect
    from redirects.pathutils import normalize_path

    skus_unpublished = 0
    redirects = 0

    for body in LEGACY_FLANGED_BODY_CODES:
        legacy_code = f"8100-{body.lower()}"
        legacy_sku = (
            SKU.objects.filter(sku_code__iexact=legacy_code).select_related("product", "product__category").first()
        )
        target = (
            SKU.objects.filter(sku_code__iexact=f"H8103-{body}-24A")
            .select_related("product", "product__category")
            .first()
        )
        if legacy_sku is not None and legacy_sku.is_published:
            legacy_sku.is_published = False
            legacy_sku.save(update_fields=["is_published"])
            skus_unpublished += 1

        if legacy_sku is None or target is None:
            continue
        from_path = normalize_path(catalog_path_for_sku(legacy_sku))
        to_path = normalize_path(catalog_path_for_sku(target))
        if not from_path or not to_path or from_path == to_path:
            continue
        _, created = Redirect.objects.update_or_create(
            from_path=from_path,
            defaults={
                "to_path": to_path,
                "status_code": 301,
                "is_active": True,
            },
        )
        if created:
            redirects += 1
        flat_norm = normalize_path(f"/{product_slug_for_series(body)}")
        if flat_norm and flat_norm != to_path:
            _, flat_created = Redirect.objects.update_or_create(
                from_path=flat_norm,
                defaults={
                    "to_path": to_path,
                    "status_code": 301,
                    "is_active": True,
                },
            )
            if flat_created:
                redirects += 1

    return {"skus_unpublished": skus_unpublished, "redirects": redirects}


def apply_all_ball_valve_enrichment(
    *,
    import_images: bool = True,
    series_codes: tuple[str, ...] | None = None,
    csv_path: Path | None = None,
    attach_pdf: bool = True,
) -> dict[str, int]:
    """Enrich brass bodies, H8101…H8122 kits, and H8205 LAV cards.

    Creates missing Product/SKU rows, rewrites copy / ТТХ / media, then retires
    mistaken ``8100-bv265…2150`` body cards (not brass ``8100-bv215*``).

    Args:
        import_images: Download Tilda galleries / attach local catalog photos.
        series_codes: Optional filter like ``("BV220", "H8101", "H8205")``.
        csv_path: Optional CSV override for brass series.
        attach_pdf: Attach 2026 catalog PDF to each SKU once.

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
        "pdf_attached": 0,
        "legacy_unpublished": 0,
        "redirects": 0,
    }

    do_pdf = attach_pdf
    if do_pdf and CATALOG_PDF_PATH.is_file():
        from catalog.validators import MAX_PRODUCT_FILE_SIZE_BYTES

        if CATALOG_PDF_PATH.stat().st_size > MAX_PRODUCT_FILE_SIZE_BYTES:
            do_pdf = False

    brass_touched: list[str] = []
    for series in load_all_ball_valve_series(csv_path):
        if wanted is not None and series.code not in wanted:
            continue
        stats = apply_series_enrichment(
            series,
            import_images=import_images,
            attach_pdf=do_pdf,
        )
        if stats["products"] == 0:
            logger.warning("Product missing for %s (%s)", series.code, series.product_slug)
            continue
        brass_touched.append(series.code)
        totals["series"] += 1
        for key in (
            "products",
            "skus",
            "attributes",
            "images_created",
            "images_failed",
            "pdf_attached",
        ):
            totals[key] += stats.get(key, 0)

    if brass_touched:
        brass_merge = merge_brass_bv_onto_dn_products(
            series_codes=tuple(brass_touched),
        )
        totals["redirects"] += int(brass_merge.get("redirects", 0))
        totals["legacy_unpublished"] += int(brass_merge.get("products_retired", 0))

    kit_prefixes: set[str] = set()
    for kit in flanged_kit_series():
        if wanted is not None and not _kit_matches_filter(kit, wanted):
            continue
        stats = apply_flanged_kit_enrichment(
            kit,
            import_images=False,
            attach_pdf=do_pdf,
        )
        if stats["products"] == 0:
            logger.warning("Kit product missing for %s", kit.code)
            continue
        kit_prefixes.add(kit.kit.upper())
        totals["series"] += 1
        for key in (
            "products",
            "skus",
            "attributes",
            "images_created",
            "images_failed",
            "pdf_attached",
        ):
            totals[key] += stats.get(key, 0)

    if import_images and kit_prefixes:
        from catalog.etl.h81_catalog_media import apply_h81_catalog_media

        media = apply_h81_catalog_media(prefixes=tuple(sorted(kit_prefixes)))
        totals["images_created"] += int(media.get("created", 0))

    if kit_prefixes:
        merge = merge_h81_kits_onto_family_products(
            prefixes=tuple(sorted(kit_prefixes)),
        )
        totals["redirects"] = totals.get("redirects", 0) + int(merge.get("redirects", 0))
        totals["legacy_unpublished"] = totals.get("legacy_unpublished", 0) + int(
            merge.get("products_retired", 0),
        )

    lav_seeded = False
    for lav in all_h8205_series():
        if wanted is not None and not _lav_matches_filter(lav, wanted):
            continue
        stats = apply_h8205_lav_enrichment(lav, attach_pdf=do_pdf)
        if stats["products"] == 0:
            logger.warning("H8205 product missing for %s", lav.code)
            continue
        lav_seeded = True
        totals["series"] += 1
        for key in (
            "products",
            "skus",
            "attributes",
            "images_created",
            "images_failed",
            "pdf_attached",
        ):
            totals[key] += stats.get(key, 0)

    if import_images and lav_seeded:
        from catalog.etl.h8205_catalog_media import apply_h8205_catalog_media

        media = apply_h8205_catalog_media()
        totals["images_created"] += int(media.get("created", 0))

    if kit_prefixes or lav_seeded:
        totals["redirects"] = totals.get("redirects", 0) + ensure_h81_kit_category_redirects()

    run_retire = wanted is None or any(
        c.startswith("H810") or c.startswith("H812") or c in LEGACY_FLANGED_BODY_CODES for c in (wanted or set())
    )
    if run_retire:
        retired = retire_legacy_flanged_body_skus()
        totals["legacy_unpublished"] = totals.get("legacy_unpublished", 0) + retired["skus_unpublished"]
        totals["redirects"] = totals.get("redirects", 0) + retired["redirects"]
    return totals
