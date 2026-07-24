"""H81 factory kit matrices (H8101…H8122), excluding H8205 LAV.

Catalog 2026 шаровые: standard/fast pairs with glued electrical tails
``…-24AS`` / ``…-230D`` (no hyphen before A/D).

Brass bodies keep separate ``8100-bv*`` cards; kits are additional SKUs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

KIT_VOLTAGES: tuple[str, ...] = ("24", "230")
KIT_CONTROL_SUFFIXES: tuple[str, ...] = ("A", "AS", "D", "DS")

# body+letter, dn, kvs, ways — matches published 8100-bv* editions.
BRASS_KIT_BODIES: tuple[tuple[str, str, str, str], ...] = (
    ("BV215A", "15", "1,6", "2-ходовый"),
    ("BV215B", "15", "2,5", "2-ходовый"),
    ("BV215C", "15", "4,0", "2-ходовый"),
    ("BV215D", "15", "6,3", "2-ходовый"),
    ("BV215E", "15", "10,1", "2-ходовый"),
    ("BV220A", "20", "1,6", "2-ходовый"),
    ("BV220B", "20", "2,5", "2-ходовый"),
    ("BV220C", "20", "4,0", "2-ходовый"),
    ("BV220D", "20", "6,3", "2-ходовый"),
    ("BV220E", "20", "10,1", "2-ходовый"),
    ("BV225A", "25", "10", "2-ходовый"),
    ("BV225B", "25", "16", "2-ходовый"),
    ("BV232A", "32", "16", "2-ходовый"),
    ("BV232B", "32", "25", "2-ходовый"),
    ("BV240A", "40", "25", "2-ходовый"),
    ("BV240B", "40", "40", "2-ходовый"),
    ("BV250A", "50", "40", "2-ходовый"),
    ("BV250B", "50", "63", "2-ходовый"),
    ("BV315A", "15", "1,6", "3-ходовый"),
    ("BV315B", "15", "2,5", "3-ходовый"),
    ("BV315C", "15", "4,0", "3-ходовый"),
    ("BV315D", "15", "6,3", "3-ходовый"),
    ("BV315E", "15", "10,1", "3-ходовый"),
    ("BV320A", "20", "1,6", "3-ходовый"),
    ("BV320B", "20", "2,5", "3-ходовый"),
    ("BV320C", "20", "4,0", "3-ходовый"),
    ("BV320D", "20", "6,3", "3-ходовый"),
    ("BV320E", "20", "10,1", "3-ходовый"),
    ("BV325A", "25", "10", "3-ходовый"),
    ("BV325B", "25", "16", "3-ходовый"),
    ("BV332A", "32", "16", "3-ходовый"),
    ("BV332B", "32", "25", "3-ходовый"),
    ("BV340A", "40", "25", "3-ходовый"),
    ("BV340B", "40", "40", "3-ходовый"),
    ("BV350A", "50", "40", "3-ходовый"),
    ("BV350B", "50", "63", "3-ходовый"),
)

_BRASS_THREAD_BY_DN: dict[str, str] = {
    "15": "внутренняя G 1/2",
    "20": "внутренняя G 3/4",
    "25": "внутренняя G 1",
    "32": "внутренняя G 1-1/4",
    "40": "внутренняя G 1-1/2",
    "50": "внутренняя G 2",
}

# body, dn, kvs, L, D, H, H1 — H8103/04 and H8107/08 (catalog dims).
FLANGED_STD_BODY_ROWS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("BV265", "65", "63", "93", "105", "259", "67"),
    ("BV280", "80", "100", "108", "125", "267", "90"),
    ("BV2100", "100", "160", "120", "148", "230", "99"),
    ("BV2125", "125", "250", "145", "179", "244", "114"),
    ("BV2150", "150", "400", "168", "205", "258", "138"),
)

# H8121/22 — different L/D/H/H1 and Kvs (catalog p.23).
FLANGED_H8121_BODY_ROWS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("BV265", "65", "110", "159", "185", "217", "119"),
    ("BV280", "80", "160", "191", "200", "227", "129"),
    ("BV2100", "100", "220", "204", "220", "245", "147"),
    ("BV2125", "125", "330", "235", "250", "258", "160"),
    ("BV2150", "150", "417", "269", "285", "268", "170"),
)


@dataclass(frozen=True, slots=True)
class KitFamily:
    """One H81xx standard/fast pair member."""

    prefix: str
    speed_label: str
    run_time: str
    ip_rating: str
    drive_note: str
    body_kind: str  # brass | flanged_std | flanged_h8121
    material: str
    connection: str
    power_std: str
    power_fast_small: str
    power_fast_large: str
    # Inclusive DN bands for families with split power tables (H8101/02/05).
    power_bands: tuple[tuple[int, int, str], ...] = ()
    # Inclusive DN bands for split run-time tables (H8105).
    run_time_bands: tuple[tuple[int, int, str], ...] = ()


KIT_FAMILIES: tuple[KitFamily, ...] = (
    KitFamily(
        prefix="H8101",
        speed_label="стандартная",
        run_time="< 60 с",
        ip_rating="IP54",
        drive_note="HV",
        body_kind="brass",
        material="Латунь",
        connection="внутренняя резьба PN20",
        power_std="",
        power_fast_small="",
        power_fast_large="",
        power_bands=(
            (15, 25, "В рабочем режиме: 3 Вт / В режиме ожидания: 1 Вт"),
            (32, 50, "В рабочем режиме: 4,5 Вт / В режиме ожидания: 1 Вт"),
        ),
    ),
    KitFamily(
        prefix="H8102",
        speed_label="быстродействующая",
        run_time="< 20 с",
        ip_rating="IP54",
        drive_note="HV",
        body_kind="brass",
        material="Латунь",
        connection="внутренняя резьба PN20",
        power_std="",
        power_fast_small="",
        power_fast_large="",
        power_bands=(
            (15, 25, "В рабочем режиме: 3,5 Вт / В режиме ожидания: 1 Вт"),
            (32, 50, "В рабочем режиме: 5 Вт / В режиме ожидания: 1 Вт"),
        ),
    ),
    KitFamily(
        prefix="H8103",
        speed_label="стандартная",
        run_time="< 150 с",
        ip_rating="IP54",
        drive_note="DA",
        body_kind="flanged_std",
        material="ВЧШГ",
        connection="фланцевое PN16",
        power_std="В рабочем режиме: 5 Вт / В режиме ожидания: 1 Вт",
        power_fast_small="",
        power_fast_large="",
    ),
    KitFamily(
        prefix="H8104",
        speed_label="быстродействующая",
        run_time="< 20 с",
        ip_rating="IP54",
        drive_note="DA",
        body_kind="flanged_std",
        material="ВЧШГ",
        connection="фланцевое PN16",
        power_std="",
        power_fast_small="В рабочем режиме: 8 Вт / В режиме ожидания: 1 Вт",
        power_fast_large="В рабочем режиме: 15 Вт / В режиме ожидания: 3 Вт",
    ),
    KitFamily(
        prefix="H8105",
        speed_label="стандартная",
        run_time="",
        ip_rating="IP44",
        drive_note="DA",
        body_kind="brass",
        material="Латунь",
        connection="внутренняя резьба PN20",
        power_std="",
        power_fast_small="",
        power_fast_large="",
        power_bands=(
            (15, 32, "В рабочем режиме: 3 Вт / ожидание: 0,8 Вт"),
            (40, 50, "В рабочем режиме: 4,5 Вт / ожидание: 1,0 Вт"),
        ),
        run_time_bands=(
            (15, 20, "< 50 с"),
            (25, 32, "< 70 с"),
            (40, 50, "< 55 с"),
        ),
    ),
    KitFamily(
        prefix="H8106",
        speed_label="быстродействующая",
        run_time="< 10 с",
        ip_rating="IP44",
        drive_note="DA",
        body_kind="brass",
        material="Латунь",
        connection="внутренняя резьба PN20",
        power_std="В рабочем режиме: 12 Вт / В режиме ожидания: 1 Вт",
        power_fast_small="",
        power_fast_large="",
    ),
    KitFamily(
        prefix="H8107",
        speed_label="стандартная",
        run_time="< 150 с",
        ip_rating="IP54",
        drive_note="DA",
        body_kind="flanged_std",
        material="ВЧШГ",
        connection="фланцевое PN16",
        power_std="В рабочем режиме: 5 Вт / В режиме ожидания: 1 Вт",
        power_fast_small="",
        power_fast_large="",
    ),
    KitFamily(
        prefix="H8108",
        speed_label="быстродействующая",
        run_time="< 20 с",
        ip_rating="IP54",
        drive_note="DA",
        body_kind="flanged_std",
        material="ВЧШГ",
        connection="фланцевое PN16",
        power_std="",
        power_fast_small="В рабочем режиме: 8 Вт / В режиме ожидания: 1 Вт",
        power_fast_large="В рабочем режиме: 15 Вт / В режиме ожидания: 3 Вт",
    ),
    KitFamily(
        prefix="H8121",
        speed_label="стандартная",
        run_time="< 150 с",
        ip_rating="IP54",
        drive_note="HV",
        body_kind="flanged_h8121",
        material="ВЧШГ",
        connection="фланцевое PN16",
        power_std="В рабочем режиме: 5 Вт / В режиме ожидания: 1 Вт",
        power_fast_small="",
        power_fast_large="",
    ),
    KitFamily(
        prefix="H8122",
        speed_label="быстродействующая",
        run_time="< 20 с",
        ip_rating="IP54",
        drive_note="HV",
        body_kind="flanged_h8121",
        material="ВЧШГ",
        connection="фланцевое PN16",
        power_std="",
        power_fast_small="В рабочем режиме: 8 Вт / В режиме ожидания: 1 Вт",
        power_fast_large="В рабочем режиме: 15 Вт / В режиме ожидания: 3 Вт",
    ),
)


@dataclass(frozen=True)
class H81KitSeries:
    """One H81xx × body matrix row (SKU editions share one family Product)."""

    family: KitFamily
    body: str
    dn: str
    kvs: str
    ways: str
    thread: str
    valve_length: str
    valve_od: str
    height_actuator: str
    height_stem: str
    diff_pressure: str = "0,35"
    gallery_local_files: tuple[str, ...] = ()

    @property
    def kit(self) -> str:
        return self.family.prefix

    @property
    def code(self) -> str:
        return f"{self.kit}-{self.body}"

    @property
    def product_slug(self) -> str:
        """One Product per H81xx series (``h8101``), not per body."""
        return h81_family_product_slug(self.kit)

    @property
    def speed_label(self) -> str:
        return self.family.speed_label

    @property
    def run_time(self) -> str:
        """Actuator run-time for this body DN (band-aware for H8105)."""
        fam = self.family
        if fam.run_time_bands:
            return _band_value(fam.run_time_bands, int(self.dn)) or fam.run_time
        return fam.run_time

    @property
    def material(self) -> str:
        return self.family.material

    @property
    def is_brass(self) -> bool:
        return self.family.body_kind == "brass"

    @property
    def product_name(self) -> str:
        """Family-level Product title (shared by all bodies of this series)."""
        return h81_family_product_name(self.family)

    @property
    def sku_display_name(self) -> str:
        """Per-body SKU title shown on PDP for one edition."""
        text = f"{self.kit}-{self.body} | Электрический шаровой кран {self.ways} DN {self.dn}"
        return " ".join(text.split())

    def power_consumption(self, _voltage: str) -> str:
        """Actuator power line for this body DN from the family catalog table."""
        fam = self.family
        dn_n = int(self.dn)
        if fam.power_bands:
            return _band_value(fam.power_bands, dn_n) or fam.power_std
        if fam.power_std:
            return fam.power_std
        if dn_n <= 80:
            return fam.power_fast_small or fam.power_fast_large
        return fam.power_fast_large or fam.power_fast_small


def h81_family_product_slug(prefix: str) -> str:
    """Canonical Product.slug for an H81xx series (``h8101``)."""
    return (prefix or "").strip().casefold()


def h81_family_product_name(family: KitFamily) -> str:
    """Human Product name for one H81xx series card."""
    text = f"{family.prefix} | Электрический шаровой кран ({family.speed_label} серия)"
    return " ".join(text.split())


def h81_sku_slug(product_slug: str, sku_code: str) -> str:
    """Stable SKU.slug under a family Product (``h8101-h8101-bv215a-24as``)."""
    return f"{product_slug}-{(sku_code or '').strip().lower()}"


_H81_PARTS_RE = re.compile(
    r"(?i)^(?P<kit>h81(?:01|02|03|04|05|06|07|08|21|22))-"
    r"(?P<body>bv\d{3,4}[a-e]?)-"
    r"(?P<volt>24|230)(?P<ctrl>as|a|ds|d)$",
)


def parse_h81_kit_parts(sku_code: str) -> dict[str, str] | None:
    """Parse kit / body / voltage / control from an H81 factory SKU code.

    Returns:
        Dict with ``kit``, ``body``, ``volt``, ``ctrl`` (uppercase kit/body),
        or ``None`` when the code is not an H81 edition.
    """
    match = _H81_PARTS_RE.fullmatch((sku_code or "").strip())
    if match is None:
        return None
    return {
        "kit": match.group("kit").upper(),
        "body": match.group("body").upper(),
        "volt": match.group("volt"),
        "ctrl": match.group("ctrl").lower(),
    }


def body_meta_for_h81(kit_prefix: str, body: str) -> tuple[str, str, str] | None:
    """Return ``(dn, kvs, ways)`` for a kit body code, or ``None``.

    Args:
        kit_prefix: ``H8101`` … ``H8122``.
        body: ``BV215A`` / ``BV265`` / …

    Returns:
        DN, Kvs, ways label when the body belongs to that family's matrix.
    """
    prefix = (kit_prefix or "").strip().upper()
    body_u = (body or "").strip().upper()
    family = next((f for f in KIT_FAMILIES if f.prefix == prefix), None)
    if family is None:
        return None
    if family.body_kind == "brass":
        for row_body, dn, kvs, ways in BRASS_KIT_BODIES:
            if row_body == body_u:
                return dn, kvs, ways
        return None
    rows = FLANGED_H8121_BODY_ROWS if family.body_kind == "flanged_h8121" else FLANGED_STD_BODY_ROWS
    for row_body, dn, kvs, *_rest in rows:
        if row_body == body_u:
            return dn, kvs, "2-ходовый"
    return None


def _band_value(bands: tuple[tuple[int, int, str], ...], dn: int) -> str:
    """Return the first band text whose inclusive DN range covers ``dn``."""
    for lo, hi, text in bands:
        if lo <= dn <= hi:
            return text
    return bands[-1][2] if bands else ""


def h81_kit_edition_sku_codes(kit: H81KitSeries) -> list[str]:
    """Eight electrical editions for one kit × body row."""
    return [f"{kit.kit}-{kit.body}-{voltage}{suffix}" for voltage in KIT_VOLTAGES for suffix in KIT_CONTROL_SUFFIXES]


def all_h81_kit_series(
    *,
    gallery_flanged: tuple[str, ...] = (),
) -> list[H81KitSeries]:
    """Build all H8101…H8122 body rows (SKU matrix; Product is per family)."""
    out: list[H81KitSeries] = []
    for family in KIT_FAMILIES:
        if family.body_kind == "brass":
            for body, dn, kvs, ways in BRASS_KIT_BODIES:
                thread = _BRASS_THREAD_BY_DN.get(dn, family.connection)
                out.append(
                    H81KitSeries(
                        family=family,
                        body=body,
                        dn=dn,
                        kvs=kvs,
                        ways=ways,
                        thread=thread,
                        valve_length="",
                        valve_od="",
                        height_actuator="",
                        height_stem="",
                        gallery_local_files=(),
                    ),
                )
        elif family.body_kind == "flanged_std":
            rows = FLANGED_STD_BODY_ROWS
            for body, dn, kvs, length, od, h_act, h_stem in rows:
                out.append(
                    H81KitSeries(
                        family=family,
                        body=body,
                        dn=dn,
                        kvs=kvs,
                        ways="2-ходовый",
                        thread=family.connection,
                        valve_length=length,
                        valve_od=od,
                        height_actuator=h_act,
                        height_stem=h_stem,
                        gallery_local_files=gallery_flanged,
                    ),
                )
        elif family.body_kind == "flanged_h8121":
            for body, dn, kvs, length, od, h_act, h_stem in FLANGED_H8121_BODY_ROWS:
                out.append(
                    H81KitSeries(
                        family=family,
                        body=body,
                        dn=dn,
                        kvs=kvs,
                        ways="2-ходовый",
                        thread=family.connection,
                        valve_length=length,
                        valve_od=od,
                        height_actuator=h_act,
                        height_stem=h_stem,
                        gallery_local_files=gallery_flanged,
                    ),
                )
    return out


def h81_family_prefixes() -> tuple[str, ...]:
    """Ordered H8101…H8122 prefixes (one Product each)."""
    return tuple(family.prefix for family in KIT_FAMILIES)


def is_h81_kit_sku_code(sku_code: str) -> bool:
    """True for complete H8101…H8122 valve+actuator articles (not H8205)."""
    return parse_h81_kit_parts(sku_code) is not None
