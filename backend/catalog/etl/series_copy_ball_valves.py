"""Canonical copy + ТТХ for Hoocon ball valves.

* Brass bodies (``8100-bv*``): valve only + RFQ kit picker.
* H81 factory kits (**H8101…H8122**): complete valve+actuator editions
  ``H8101-BV215A-24AS`` … ``H8122-BV2150-230DS`` (H8205 LAV is separate).

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
from catalog.etl.h81_kits import (
    FLANGED_STD_BODY_ROWS,
    H81KitSeries,
    all_h81_kit_series,
    h81_kit_edition_sku_codes,
    is_h81_kit_sku_code,
)
from catalog.etl.sku_variant import parse_sku_variant
from catalog.etl.tech_copy import (
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
CATALOG_PDF_PATH = (_REPO_ROOT / "_инструкции-pdf" / "каталог_2026_шаровые_hoocon_ver_1.05.pdf").resolve()


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


def product_slug_for_flanged_kit(kit: str, body: str) -> str:
    """Return product slug for an H81 kit card (``sharovoy-kran-h8103-bv265``)."""
    return f"sharovoy-kran-{kit.casefold()}-{body.casefold()}"


def ball_valve_product_slugs() -> frozenset[str]:
    """All known ball-valve product slugs (brass bodies + H81 kits)."""
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
    kit_slugs = (card.product_slug for card in all_h81_kit_series())
    return frozenset(
        (*(product_slug_for_series(f"BV{n}") for n in brass), *kit_slugs),
    )


def is_flanged_kit_sku_code(sku_code: str) -> bool:
    """True for complete H8101…H8122 valve+actuator article codes."""
    return is_h81_kit_sku_code(sku_code)


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
– Рабочая среда (по умолчанию): холодная и горячая вода;
  по спецзаказу — с содержанием этиленгликоля не более 50 %.
– Рабочая температура среды: –9…+95 °C.
– {join_label}: {series.thread}.
– Материал корпуса: {series.material}.
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
    join_label = "соединение" if series.is_flanged else "резьба"
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
            f"{join_label} {series.thread}."
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
        aux_val = normalize_aux_switch_value("SPDT-1")
        _set_attr(sku, "Вспомогательный переключатель", "aux-switch", "", aux_val)
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
        if SKU.objects.filter(sku_code__iexact=sku_code).exists():
            continue
        slug = f"{series.product_slug}-{sku_code.lower()}"
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
– Рабочая среда (по умолчанию): холодная и горячая вода;
  по спецзаказу — с содержанием этиленгликоля не более 50 %.
– Рабочая температура среды: –9…+95 °C.
– {join_label}: {kit.thread}.
– Материал корпуса: {kit.material}.
– Вид: {kit.ways}.
– Время срабатывания: {kit.run_time}.
– Степень защиты привода: {kit.family.ip_rating}.
– Ручное управление: есть.
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


def _kit_sku_description(kit: H81KitSeries, sku_code: str) -> str:
    variant = parse_sku_variant(sku_code)
    control_label = "плавное (аналоговое)" if variant.control == "modulating" else "открыто/закрыто"
    aux_label = "с вспомогательным переключателем" if variant.aux_switch else ("без вспомогательного переключателя")
    volt = variant.voltage or "?"
    join_word = "резьба" if kit.is_brass else "соединение"
    lines = [
        (
            f"Электрический шаровой кран {kit.ways} DN {kit.dn} "
            f"{kit.kit}-{kit.body} ({kit.speed_label} серия) для систем "
            "отопления, вентиляции и кондиционирования (HVAC)."
        ),
        f"Пропускная способность: Kvs {kit.kvs} м³/ч.",
        (
            "Рабочая среда — холодная и горячая вода "
            "(этиленгликоль ≤ 50 % по спецзаказу); "
            f"температура среды –9…+95 °C; "
            f"{join_word} {kit.thread}."
        ),
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
        "Гарантия: 24 месяца.",
    ]
    return normalize_tech_copy("\n".join(lines))


def ensure_flanged_kit_series(kit: FlangedKitSeries) -> dict[str, int]:
    """Create missing Product + 8 electrical SKUs for one H81 kit card."""
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
            description=_kit_series_description(kit),
        )
        products_created = 1
    else:
        product.category = category
        product.save(update_fields=["category"])

    for sku_code in flanged_kit_edition_sku_codes(kit):
        if SKU.objects.filter(sku_code__iexact=sku_code).exists():
            continue
        slug_sku = f"{kit.product_slug}-{sku_code.lower()}"
        if SKU.objects.filter(slug=slug_sku).exists():
            slug_sku = f"{slug_sku}-{SKU.objects.count()}"
        SKU.objects.create(
            product=product,
            name=kit.product_name[:300],
            slug=slug_sku[:300],
            sku_code=sku_code,
            description="",
            is_published=True,
        )
        skus_created += 1
    return {"products_created": products_created, "skus_created": skus_created}


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
    """Seed + rewrite one H81 kit product (8 electrical editions).

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
    product.description = _kit_series_description(kit)
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
        sku.name = kit.product_name[:300]
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
    """Enrich brass body series + H8101…H8122 factory kits.

    Creates missing Product/SKU rows, rewrites copy / ТТХ / media, then retires
    mistaken ``8100-bv265…2150`` body cards (not brass ``8100-bv215*``).

    Args:
        import_images: Download Tilda galleries / attach local catalog photos.
        series_codes: Optional filter like ``("BV220", "H8101", "H8121")``.
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
        totals["redirects"] = totals.get("redirects", 0) + ensure_h81_kit_category_redirects()

    run_retire = wanted is None or any(
        c.startswith("H810") or c.startswith("H812") or c in LEGACY_FLANGED_BODY_CODES for c in (wanted or set())
    )
    if run_retire:
        retired = retire_legacy_flanged_body_skus()
        totals["legacy_unpublished"] = retired["skus_unpublished"]
        totals["redirects"] = totals.get("redirects", 0) + retired["redirects"]
    return totals
