"""H8205 LAV electric regulating valves (catalog 2026 шаровые, p.26–29).

One Product card per dimensions-table row (``LAV232``…``LAV3300``).
Electrical editions inside the card::

    H8205-LAV{ways}{dn}{opts}-{24|230}{A|D|M}

``opts`` ∈ ``"" | S | T | ST`` (aux switch / fault alarm).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LAV_VOLTAGES: tuple[str, ...] = ("24", "230")
LAV_CONTROLS: tuple[str, ...] = ("A", "D", "M")
LAV_OPTION_SUFFIXES: tuple[str, ...] = ("", "S", "T", "ST")

# body, ways_digit, dn, ways_label, C, L, H, H1, H2,
# pn16_od, pn16_pcd, pn16_bolts, pn25_od, pn25_pcd, pn25_bolts, flange_face_f
_LavRow = tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
]


def _row(
    body: str,
    ways_digit: str,
    dn: str,
    ways: str,
    face_c: str,
    length_l: str,
    height_h: str,
    height_h1: str,
    height_h2: str,
    pn16_od: str,
    pn16_pcd: str,
    pn16_bolts: str,
    pn25_od: str,
    pn25_pcd: str,
    pn25_bolts: str,
    flange_f: str,
) -> _LavRow:
    """Build one catalog dimensions-table row."""
    return (
        body,
        ways_digit,
        dn,
        ways,
        face_c,
        length_l,
        height_h,
        height_h1,
        height_h2,
        pn16_od,
        pn16_pcd,
        pn16_bolts,
        pn25_od,
        pn25_pcd,
        pn25_bolts,
        flange_f,
    )


LAV_BODY_ROWS: tuple[_LavRow, ...] = (
    _row(
        "LAV232",
        "2",
        "32",
        "2-ходовый",
        "18",
        "180",
        "318",
        "119",
        "",
        "140",
        "100",
        "4×Ø18",
        "140",
        "100",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV240",
        "2",
        "40",
        "2-ходовый",
        "18",
        "200",
        "318",
        "129",
        "",
        "150",
        "110",
        "4×Ø18",
        "150",
        "110",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV250",
        "2",
        "50",
        "2-ходовый",
        "20",
        "230",
        "358",
        "146",
        "",
        "165",
        "125",
        "4×Ø18",
        "165",
        "125",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV265",
        "2",
        "65",
        "2-ходовый",
        "20",
        "290",
        "373",
        "178",
        "",
        "185",
        "145",
        "4×Ø18",
        "185",
        "145",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV280",
        "2",
        "80",
        "2-ходовый",
        "20",
        "310",
        "446",
        "190",
        "",
        "200",
        "160",
        "8×Ø18",
        "200",
        "160",
        "8×Ø18",
        "3",
    ),
    _row(
        "LAV2100",
        "2",
        "100",
        "2-ходовый",
        "22",
        "350",
        "477",
        "206",
        "",
        "220",
        "180",
        "8×Ø18",
        "235",
        "190",
        "8×Ø22",
        "3",
    ),
    _row(
        "LAV2125",
        "2",
        "125",
        "2-ходовый",
        "22",
        "400",
        "490",
        "233",
        "",
        "250",
        "210",
        "8×Ø18",
        "270",
        "220",
        "8×Ø26",
        "3",
    ),
    _row(
        "LAV2150",
        "2",
        "150",
        "2-ходовый",
        "24",
        "480",
        "517",
        "275",
        "",
        "285",
        "240",
        "8×Ø22",
        "300",
        "250",
        "8×Ø26",
        "3",
    ),
    _row(
        "LAV2200",
        "2",
        "200",
        "2-ходовый",
        "24",
        "495",
        "574",
        "200",
        "",
        "340",
        "295",
        "12×Ø22",
        "360",
        "310",
        "12×Ø26",
        "3",
    ),
    _row(
        "LAV2250",
        "2",
        "250",
        "2-ходовый",
        "26",
        "622",
        "606",
        "240",
        "",
        "405",
        "355",
        "12×Ø26",
        "425",
        "370",
        "12×Ø30",
        "3",
    ),
    _row(
        "LAV2300",
        "2",
        "300",
        "2-ходовый",
        "28",
        "698",
        "741",
        "315",
        "",
        "485",
        "410",
        "12×Ø26",
        "485",
        "430",
        "16×Ø30",
        "3",
    ),
    _row(
        "LAV332",
        "3",
        "32",
        "3-ходовый",
        "18",
        "180",
        "318",
        "",
        "90",
        "140",
        "100",
        "4×Ø18",
        "140",
        "100",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV340",
        "3",
        "40",
        "3-ходовый",
        "18",
        "200",
        "318",
        "",
        "100",
        "150",
        "110",
        "4×Ø18",
        "150",
        "110",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV350",
        "3",
        "50",
        "3-ходовый",
        "20",
        "230",
        "358",
        "",
        "115",
        "165",
        "125",
        "4×Ø18",
        "165",
        "125",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV365",
        "3",
        "65",
        "3-ходовый",
        "20",
        "290",
        "373",
        "",
        "145",
        "185",
        "145",
        "4×Ø18",
        "185",
        "145",
        "4×Ø18",
        "3",
    ),
    _row(
        "LAV380",
        "3",
        "80",
        "3-ходовый",
        "20",
        "310",
        "446",
        "",
        "155",
        "200",
        "160",
        "8×Ø18",
        "200",
        "160",
        "8×Ø18",
        "3",
    ),
    _row(
        "LAV3100",
        "3",
        "100",
        "3-ходовый",
        "22",
        "350",
        "477",
        "",
        "175",
        "220",
        "180",
        "8×Ø18",
        "235",
        "190",
        "8×Ø22",
        "3",
    ),
    _row(
        "LAV3125",
        "3",
        "125",
        "3-ходовый",
        "22",
        "400",
        "490",
        "",
        "200",
        "250",
        "210",
        "8×Ø18",
        "270",
        "220",
        "8×Ø26",
        "3",
    ),
    _row(
        "LAV3150",
        "3",
        "150",
        "3-ходовый",
        "24",
        "480",
        "517",
        "",
        "240",
        "285",
        "240",
        "8×Ø22",
        "300",
        "250",
        "8×Ø26",
        "3",
    ),
    _row(
        "LAV3200",
        "3",
        "200",
        "3-ходовый",
        "24",
        "495",
        "574",
        "",
        "172",
        "340",
        "295",
        "12×Ø22",
        "360",
        "310",
        "12×Ø26",
        "3",
    ),
    _row(
        "LAV3250",
        "3",
        "250",
        "3-ходовый",
        "26",
        "622",
        "606",
        "",
        "203",
        "405",
        "355",
        "12×Ø26",
        "425",
        "370",
        "12×Ø30",
        "3",
    ),
    _row(
        "LAV3300",
        "3",
        "300",
        "3-ходовый",
        "28",
        "698",
        "741",
        "",
        "285",
        "485",
        "410",
        "12×Ø26",
        "485",
        "430",
        "16×Ø30",
        "3",
    ),
)

_H8205_SKU_RE = re.compile(
    r"(?i)^h8205-(?P<body>lav[23](?:32|40|50|65|80|100|125|150|200|250|300))"
    r"(?P<opts>st|s|t)?"
    r"-(?P<volt>24|230)(?P<ctrl>a|d|m)$",
)

MATERIAL_BODY = "Ковкий чугун (с шаровидным графитом)"
MATERIAL_STEM = "Нержавеющая сталь 304"
MATERIAL_PLUG = "Нержавеющая сталь 304"
MATERIAL_SEAT = "Нержавеющая сталь 304"
MATERIAL_SEAL = "EPDM"
CONNECTION = "Фланцевое (GB/T17241.6)"
PRESSURE_RATING = "PN16, PN25"
MEDIUM_TEMP = "–20 … +150 °C"
MEDIUM = "Вода, раствор этиленгликоля концентрацией менее 50%"
LEAKAGE = "0…0,02% от Kvs"
FLOW_CHAR = "Равнопроцентная, линейная"


@dataclass(frozen=True, slots=True)
class H8205LavSeries:
    """One H8205-LAV* product card (dimensions-table row)."""

    body: str
    ways_digit: str
    dn: str
    ways: str
    face_to_face_c: str
    length_l: str
    height_h: str
    height_h1: str
    height_h2: str
    pn16_od: str
    pn16_pcd: str
    pn16_bolts: str
    pn25_od: str
    pn25_pcd: str
    pn25_bolts: str
    flange_face_f: str

    @property
    def code(self) -> str:
        return f"H8205-{self.body}"

    @property
    def product_slug(self) -> str:
        return f"h8205-{self.body.casefold()}"

    @property
    def product_name(self) -> str:
        text = f"{self.code} | Электрический регулирующий клапан {self.ways} DN {self.dn}"
        return " ".join(text.split())


def h8205_edition_sku_codes(series: H8205LavSeries) -> list[str]:
    """Twenty-four electrical editions for one LAV body card."""
    codes: list[str] = []
    for opts in LAV_OPTION_SUFFIXES:
        for voltage in LAV_VOLTAGES:
            for ctrl in LAV_CONTROLS:
                codes.append(f"H8205-{series.body}{opts}-{voltage}{ctrl}")
    return codes


def all_h8205_series() -> list[H8205LavSeries]:
    """Build all 22 H8205 LAV product cards from the catalog table."""
    out: list[H8205LavSeries] = []
    for row in LAV_BODY_ROWS:
        (
            body,
            ways_digit,
            dn,
            ways,
            face_c,
            length_l,
            height_h,
            height_h1,
            height_h2,
            pn16_od,
            pn16_pcd,
            pn16_bolts,
            pn25_od,
            pn25_pcd,
            pn25_bolts,
            flange_f,
        ) = row
        out.append(
            H8205LavSeries(
                body=body,
                ways_digit=ways_digit,
                dn=dn,
                ways=ways,
                face_to_face_c=face_c,
                length_l=length_l,
                height_h=height_h,
                height_h1=height_h1,
                height_h2=height_h2,
                pn16_od=pn16_od,
                pn16_pcd=pn16_pcd,
                pn16_bolts=pn16_bolts,
                pn25_od=pn25_od,
                pn25_pcd=pn25_pcd,
                pn25_bolts=pn25_bolts,
                flange_face_f=flange_f,
            ),
        )
    return out


def is_h8205_sku_code(sku_code: str) -> bool:
    """True for complete H8205-LAV electrical editions."""
    return bool(_H8205_SKU_RE.fullmatch((sku_code or "").strip()))


def parse_h8205_sku_parts(sku_code: str) -> dict[str, str] | None:
    """Parse body / opts / voltage / control from an H8205 SKU code.

    Returns:
        Dict with keys ``body``, ``opts``, ``volt``, ``ctrl`` (uppercase body,
        lowercase ctrl), or ``None`` when the code is not an H8205 edition.
    """
    match = _H8205_SKU_RE.fullmatch((sku_code or "").strip())
    if match is None:
        return None
    return {
        "body": match.group("body").upper(),
        "opts": (match.group("opts") or "").upper(),
        "volt": match.group("volt"),
        "ctrl": match.group("ctrl").lower(),
    }
