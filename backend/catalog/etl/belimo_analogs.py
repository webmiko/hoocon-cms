"""Belimo analog codes.

The public card shows only ``SKU.analog_belimo_code``: the engineer sets it
after checking ``AnalogMap`` (or the datasheet) when the card is created.
Runtime does not re-read ``AnalogMap`` rows or infer codes from card copy.
``AnalogMap`` stays an admin reference for that manual check.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from catalog.etl.html_text import filter_analogs_for_sku
from catalog.etl.sku_variant import parse_hva_code, parse_sku_variant, sku_code_is_thermal

if TYPE_CHECKING:
    from catalog.models import SKU

Purpose = Literal[
    "air_no_spring",
    "air_spring",
    "fire_spring",
    "fast",
    "electronic_failsafe",
    "smoke",
    "valve",
    "unknown",
]

# «– Belimo LF24-S» / «Belimo NF24A» / bare after brand.
_BELIMO_LINE = re.compile(
    r"(?i)\bBelimo\s+([A-Za-z][A-Za-z0-9./\-–—−]*)",
)
_TRAILING_PUNCT = re.compile(r"[.,;:]+$")
_HAS_230 = re.compile(r"(?:^|[^0-9])230(?:[^0-9]|$)")
_HAS_24 = re.compile(r"(?:^|[^0-9])24(?:[^0-9]|$)")
_MOMENT_NUM = re.compile(r"(\d+[.,]?\d*)")
_AREA_NUM = re.compile(r"(\d+[.,]?\d*)")
# Fire thermoelectric trip is ``-T`` / ``-FST`` (``BF24-T``). A leading ``FST``
# is the US life-safety series (FSTF/FSNF), not a licence to invent ``FST-24-3N``.
# ``BEE24-ST`` ends in ``-ST`` and is a connector plug for BKNE230-24
# (datasheet BEE24-ST), not a thermal sensor.
_THERMAL_BELIMO_TOKEN = re.compile(
    r"(?:^|-)fst(?:-|$)|-t$",
)

# Belimo recommended max damper area per family, м² — EU datasheets / selection tools.
# Primary criterion: the customer picks a Belimo actuator by the damper it must move.
# Fire: motor/spring torque differs; area is still the selection key.
# Smoke BEN and BLE share the 1.5 m² area class; BEN is the primary family.
BELIMO_FAMILY_AREA: dict[str, tuple[tuple[str, float], ...]] = {
    "air_no_spring": (("TMC", 0.2), ("LM", 0.5), ("NM", 1.0), ("SM", 2.0), ("GM", 4.0)),
    "air_spring": (("TF", 0.25), ("LF", 0.4), ("NF", 1.0), ("SF", 2.0)),
    "fire_spring": (("BFL", 0.4), ("BLF", 0.5), ("BFN", 0.8), ("BF", 1.5)),
    # Fast running, non fail-safe (Belimo brochure 2026): LMQ 2.5 s / NMQ 4 s / SMQ 7 s.
    "fast": (("LMQ", 0.4), ("NMQ", 0.8), ("SMQ", 1.6), ("GMQ", 4.0)),
    # SuperCap electronic fail-safe, not the Q series above.
    # NKQ 6 Nm / 1.2 m², 24 V only; GK 40 Nm / 8 m² (fail-safe brochure 2026).
    "electronic_failsafe": (("NKQ", 1.2), ("GK", 8.0)),
    "smoke": (("BEN", 1.5), ("BEE", 2.5), ("BE", 4.0)),
}
# Every family above (+ BLE next to BEN, compact CM next to TMC) → area, м².
_FAMILY_AREA: dict[str, float] = {family: area for bands in BELIMO_FAMILY_AREA.values() for family, area in bands} | {
    "BLE": 1.5,
    "CM": 0.2,
}
_FAMILY_PREFIX = re.compile(
    r"^(" + "|".join(sorted(_FAMILY_AREA, key=len, reverse=True)) + r")(?=\d)",
)
# Fire / smoke actuators ship with 2× SPDT built in (no ``-S`` edition).
_BUILTIN_AUX_FAMILIES = frozenset(
    {f for f, _ in BELIMO_FAMILY_AREA["fire_spring"]} | {f for f, _ in BELIMO_FAMILY_AREA["smoke"]} | {"BLE"},
)
_HOOCON_NM = re.compile(r"(?i)^(?:(?:da|sa)(\d+)(?:fu|mqu|mu)|hv[ad]\d+s?t?-(\d+))")


def belimo_family_by_area(purpose: str, area_m2: float) -> str | None:
    """Largest Belimo family whose recommended area ≤ Hoocon area.

    Belimo selects actuators by damper area.  The Hoocon actuator's area
    must be **not less** than the Belimo's — we list only families the
    customer could replace with our actuator (our damper ≥ theirs).
    Above the largest family, the result stays the largest.  When even the
    smallest family is stronger than Hoocon there is no direct analog → None.
    """
    result: str | None = None
    for family, max_area in BELIMO_FAMILY_AREA.get(purpose, ()):
        if max_area <= area_m2:
            result = family
        else:
            break
    return result


# Category slug fragments → purpose for inference.
_PURPOSE_BY_CATEGORY: tuple[tuple[str, Purpose], ...] = (
    ("uskoren", "fast"),
    ("dymoudalen", "smoke"),
    ("protivopozhar", "fire_spring"),
    ("pruzhinnym-vozvrat", "air_spring"),
    ("bez-pruzhinnogo", "air_no_spring"),
    ("vozdushn", "air_no_spring"),
    ("sharov", "valve"),
    ("komplekt", "valve"),
)

# Kits (H81xx / H8205 actuator + valve) and bare 8100 ball valves get no analogs.
NO_ANALOG_CATEGORY_FRAGMENTS: tuple[str, ...] = ("komplekt", "sharov")
# Plain syntax: shared with the Postgres ``iregex`` facet filter.
NO_ANALOG_SKU_PATTERN = r"^(h81[0-9]{2}-|h8205-|8100-|bv[0-9])"
_NO_ANALOG_SKU = re.compile(NO_ANALOG_SKU_PATTERN, re.IGNORECASE)


def sku_code_takes_no_analogs(sku_code: str | None) -> bool:
    """Whether the article is a kit or a ball valve (``H8101-BV215A-24AS``, ``8100-bv215a``)."""
    return bool(_NO_ANALOG_SKU.match((sku_code or "").strip()))


def sku_takes_no_analogs(sku: SKU) -> bool:
    """Kit / ball-valve SKU by category or article: no «Аналоги» and no Belimo."""
    product = sku.product if sku.product_id else None
    category = getattr(product, "category", None)
    slug = (getattr(category, "slug", "") or "").casefold()
    return any(fragment in slug for fragment in NO_ANALOG_CATEGORY_FRAGMENTS) or sku_code_takes_no_analogs(
        sku.sku_code,
    )


def normalize_belimo_code(raw: str) -> str:
    """Normalize a Belimo article token for facet keys.

    Args:
        raw: Raw token from copy (may include unicode dashes).

    Returns:
        Uppercase article with ASCII hyphens, no trailing punctuation.
    """
    code = (raw or "").strip().replace("\xa0", " ")
    code = code.replace("−", "-").replace("—", "-").replace("–", "-")
    code = _TRAILING_PUNCT.sub("", code)
    code = " ".join(code.split())
    code = code.upper()
    # Shop spelling ``TMC230ASR`` / ``LM230ASR`` → hyphenated ``…A-SR``.
    return re.sub(r"ASR((?:-S)?)$", r"A-SR\1", code)


def extract_belimo_codes_from_text(
    text: str,
    *,
    voltage: str | None = None,
) -> list[str]:
    """Return unique Belimo article codes mentioned in analogs copy.

    Args:
        text: «Аналоги» tab / SKU analogs_text (plain).
        voltage: Optional ``24`` / ``230`` to drop mismatched articles.

    Returns:
        Ordered unique codes (first occurrence wins).
    """
    if not (text or "").strip():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _BELIMO_LINE.finditer(text):
        code = normalize_belimo_code(match.group(1))
        if not _looks_like_belimo_article(code):
            continue
        if voltage and not code_matches_voltage(code, voltage):
            continue
        if code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def code_matches_voltage(code: str, voltage: str) -> bool:
    """Return False when article voltage clearly conflicts with SKU voltage."""
    has_230 = bool(_HAS_230.search(code))
    has_24 = bool(_HAS_24.search(code)) and not has_230
    if voltage == "24" and has_230:
        return False
    if voltage == "230" and has_24:
        return False
    return True


def _looks_like_belimo_article(code: str) -> bool:
    """Reject noise tokens after the Belimo brand word."""
    if len(code) < 3 or len(code) > 32:
        return False
    if not any(ch.isdigit() for ch in code):
        return False
    if not any(ch.isalpha() for ch in code):
        return False
    return True


def infer_belimo_codes(
    *,
    purpose: Purpose,
    moment_nm: float | None,
    voltage: str | None,
    control: str | None,
    aux_spdt: int,
    thermal: bool = False,
    damper_area_m2: float | None = None,
) -> list[str]:
    """Suggest typical Belimo article(s) from actuator purpose and ТТХ.

    Belimo selects actuators by damper area first.  Torque is used only as
    a fallback (converted to area via the standard HVAC 10 N·m / m² rule).

    Args:
        purpose: Actuator family inferred from category / SKU code.
        moment_nm: Rated torque in N·m (fallback for area).
        voltage: ``24`` or ``230``.
        control: ``on_off`` / ``modulating`` / ``3_point`` (treated as on_off).
        aux_spdt: 0 / 1 / 2 auxiliary SPDT switches.
        thermal: Fire actuator with thermal fuse (DST / -T).
        damper_area_m2: Primary selection key — Hoocon SKU damper area.

    Returns:
        Zero or one primary Belimo code (list for API symmetry).
    """
    if purpose in {"valve", "unknown"} or not voltage:
        return []

    area = damper_area_m2
    if area is None and moment_nm is not None:
        # Standard HVAC rule of thumb: ~10 N·m per m².
        area = round(moment_nm / 10.0, 2)
    if area is None:
        return []

    family = belimo_family_by_area(purpose, area)
    if not family:
        return []
    code = compose_belimo_article(
        family,
        voltage=voltage,
        modulating=control == "modulating",
        aux=aux_spdt >= 1,
        thermal=thermal,
    )
    return [code] if code else []


# Factory articles only. A missing key means Belimo does not sell that
# combination — compose returns None instead of gluing a suffix.
# Sources (EU datasheets / UK shop / installation sheets), not generator output:
# - LMQ24A, LMQ24A-SR, NMQ24A-SR: AC/DC 24 V; aux is add-on S1A/S2A, not ``-S``.
# - LF24-SR (datasheet en-gb 2026-10-29). There is no LF24-RS.
# - NF24A-S2, NF24A-SR-S2 (UK shop / datasheet). Suffix is ``-S2``, two SPDT.
# - NF230A / NF230A-S2 still named on the NF..A installation sheet (2025-11);
#   the current multi-voltage replacement is NFA / NFA-S2.
# - GM24A-S and GM230A-S are the NG open/close + 1×SPDT (Belimo CZ comparison).
#   GM24S.2A is a different actuator (35 s, 2×SPST), not a rename of GM24A-S.
#   GM24A-SR-S is not in that table.
# - NM230ASR and TMC230ASR have datasheets (2025). GM230A-SR is not in the
#   NG table, so it is not emitted.
# - BEE230 / BEN24 / BE24 are on the UK smoke-control list. ``-ST`` is a
#   connector plug (BEE24-ST, BEN24-ST), not a thermoelectric trip.
#   BEN/BEE/BE have no ``-T``. BLE is discontinued and is not generated.
# - NKQ24A-1 / NKQ24A-SR, GK24A-1 / GK24A-SR: SuperCap, AC/DC 24 V only.
_CatalogKey = tuple[str, str, bool, bool, bool]

# (family, voltage, modulating, aux, thermal, article). Aux on fire/smoke is
# built in, so both aux flags point at the same literal. Nothing here is
# assembled from family + suffix.
_BELIMO_ARTICLE_ROWS: tuple[tuple[str, str, bool, bool, bool, str], ...] = (
    ("LM", "24", False, False, False, "LM24A"),
    ("LM", "24", False, True, False, "LM24A-S"),
    ("LM", "24", True, False, False, "LM24A-SR"),
    ("LM", "230", False, False, False, "LM230A"),
    ("LM", "230", False, True, False, "LM230A-S"),
    ("LM", "230", True, False, False, "LM230A-SR"),
    ("NM", "24", False, False, False, "NM24A"),
    ("NM", "24", False, True, False, "NM24A-S"),
    ("NM", "24", True, False, False, "NM24A-SR"),
    ("NM", "230", False, False, False, "NM230A"),
    ("NM", "230", False, True, False, "NM230A-S"),
    ("NM", "230", True, False, False, "NM230A-SR"),
    ("SM", "24", False, False, False, "SM24A"),
    ("SM", "24", False, True, False, "SM24A-S"),
    ("SM", "24", True, False, False, "SM24A-SR"),
    ("SM", "230", False, False, False, "SM230A"),
    ("SM", "230", False, True, False, "SM230A-S"),
    ("SM", "230", True, False, False, "SM230A-SR"),
    ("GM", "24", False, False, False, "GM24A"),
    ("GM", "24", False, True, False, "GM24A-S"),
    ("GM", "24", True, False, False, "GM24A-SR"),
    ("GM", "230", False, False, False, "GM230A"),
    ("GM", "230", False, True, False, "GM230A-S"),
    ("TMC", "24", False, False, False, "TMC24A"),
    ("TMC", "24", False, True, False, "TMC24A-S"),
    ("TMC", "24", True, False, False, "TMC24A-SR"),
    ("TMC", "230", False, False, False, "TMC230A"),
    ("TMC", "230", False, True, False, "TMC230A-S"),
    ("TMC", "230", True, False, False, "TMC230A-SR"),
    ("LMQ", "24", False, False, False, "LMQ24A"),
    ("LMQ", "24", True, False, False, "LMQ24A-SR"),
    ("NMQ", "24", False, False, False, "NMQ24A"),
    ("NMQ", "24", True, False, False, "NMQ24A-SR"),
    ("SMQ", "24", False, False, False, "SMQ24A"),
    ("SMQ", "24", True, False, False, "SMQ24A-SR"),
    ("GMQ", "24", False, False, False, "GMQ24A"),
    ("GMQ", "24", True, False, False, "GMQ24A-SR"),
    ("TF", "24", False, False, False, "TF24"),
    ("TF", "24", False, True, False, "TF24-S"),
    ("TF", "230", False, False, False, "TF230"),
    ("TF", "230", False, True, False, "TF230-S"),
    ("LF", "24", False, False, False, "LF24"),
    ("LF", "24", False, True, False, "LF24-S"),
    ("LF", "24", True, False, False, "LF24-SR"),
    ("LF", "230", False, False, False, "LF230"),
    ("LF", "230", False, True, False, "LF230-S"),
    ("NF", "24", False, False, False, "NF24A"),
    ("NF", "24", False, True, False, "NF24A-S2"),
    ("NF", "24", True, False, False, "NF24A-SR"),
    ("NF", "24", True, True, False, "NF24A-SR-S2"),
    ("NF", "230", False, False, False, "NF230A"),
    ("NF", "230", False, True, False, "NF230A-S2"),
    ("SF", "24", False, False, False, "SF24A"),
    ("SF", "24", False, True, False, "SF24A-S2"),
    ("SF", "24", True, False, False, "SF24A-SR"),
    ("SF", "24", True, True, False, "SF24A-SR-S2"),
    ("SF", "230", False, False, False, "SF230A"),
    ("SF", "230", False, True, False, "SF230A-S2"),
    ("NKQ", "24", False, False, False, "NKQ24A-1"),
    ("NKQ", "24", True, False, False, "NKQ24A-SR"),
    ("GK", "24", False, False, False, "GK24A-1"),
    ("GK", "24", True, False, False, "GK24A-SR"),
    ("BFL", "24", False, False, False, "BFL24"),
    ("BFL", "24", False, True, False, "BFL24"),
    ("BFL", "24", False, False, True, "BFL24-T"),
    ("BFL", "24", False, True, True, "BFL24-T"),
    ("BFL", "230", False, False, False, "BFL230"),
    ("BFL", "230", False, True, False, "BFL230"),
    ("BFL", "230", False, False, True, "BFL230-T"),
    ("BFL", "230", False, True, True, "BFL230-T"),
    ("BLF", "24", False, False, False, "BLF24"),
    ("BLF", "24", False, True, False, "BLF24"),
    ("BLF", "24", False, False, True, "BLF24-T"),
    ("BLF", "24", False, True, True, "BLF24-T"),
    ("BLF", "230", False, False, False, "BLF230"),
    ("BLF", "230", False, True, False, "BLF230"),
    ("BLF", "230", False, False, True, "BLF230-T"),
    ("BLF", "230", False, True, True, "BLF230-T"),
    ("BFN", "24", False, False, False, "BFN24"),
    ("BFN", "24", False, True, False, "BFN24"),
    ("BFN", "24", False, False, True, "BFN24-T"),
    ("BFN", "24", False, True, True, "BFN24-T"),
    ("BFN", "230", False, False, False, "BFN230"),
    ("BFN", "230", False, True, False, "BFN230"),
    ("BFN", "230", False, False, True, "BFN230-T"),
    ("BFN", "230", False, True, True, "BFN230-T"),
    ("BF", "24", False, False, False, "BF24"),
    ("BF", "24", False, True, False, "BF24"),
    ("BF", "24", False, False, True, "BF24-T"),
    ("BF", "24", False, True, True, "BF24-T"),
    ("BF", "230", False, False, False, "BF230"),
    ("BF", "230", False, True, False, "BF230"),
    ("BF", "230", False, False, True, "BF230-T"),
    ("BF", "230", False, True, True, "BF230-T"),
    ("BEN", "24", False, False, False, "BEN24"),
    ("BEN", "24", False, True, False, "BEN24"),
    ("BEN", "230", False, False, False, "BEN230"),
    ("BEN", "230", False, True, False, "BEN230"),
    ("BEN", "24", True, False, False, "BEN24-SR"),
    ("BEN", "24", True, True, False, "BEN24-SR"),
    ("BEE", "24", False, False, False, "BEE24"),
    ("BEE", "24", False, True, False, "BEE24"),
    ("BEE", "230", False, False, False, "BEE230"),
    ("BEE", "230", False, True, False, "BEE230"),
    ("BEE", "24", True, False, False, "BEE24-SR"),
    ("BEE", "24", True, True, False, "BEE24-SR"),
    ("BE", "24", False, False, False, "BE24"),
    ("BE", "24", False, True, False, "BE24"),
    ("BE", "230", False, False, False, "BE230"),
    ("BE", "230", False, True, False, "BE230"),
)


def _catalog() -> dict[_CatalogKey, str]:
    rows: dict[_CatalogKey, str] = {}
    for family, voltage, modulating, aux, thermal, code in _BELIMO_ARTICLE_ROWS:
        key = (family, voltage, modulating, aux, thermal)
        if key in rows:
            raise RuntimeError(f"duplicate Belimo catalog key {key}")
        rows[key] = code
    return rows


BELIMO_CATALOG: dict[_CatalogKey, str] = _catalog()

# Strings this project used to print that Belimo does not sell.
# A code outside this set is not rejected: card copy also cites real
# articles the matrix does not generate (``CM230-L/R``, ``NM24A-SR-20``).
BELIMO_NOT_ISSUED: frozenset[str] = frozenset(
    {
        "LMQ230A",
        "NMQ230A",
        "SMQ230A",
        "GMQ230A",
        "LMQ24A-S",
        "LMQ24A-SR-S",
        "NMQ24A-S",
        "NMQ24A-SR-S",
        "SMQ24A-S",
        "SMQ24A-SR-S",
        "SMQ230A",
        "SMQ230A-S",
        "GMQ24A-S",
        "GMQ24A-SR-S",
        "LM24A-SR-S",
        "NM24A-SR-S",
        "NM230A-SR-S",
        "SM24A-SR-S",
        "GM24A-SR-S",
        "GM230A-SR-S",
        "GM230A-SR",
        "LF24-RS",
        "LF230-RS",
        "LF230-SR",
        "NF24A-S",
        "NF230A-S",
        "NF24A-SR-S",
        "SF24A-S",
        "SF230A-S",
        "SF24A-SR-S",
        "BEN24-T",
        "BEN230-T",
        "BEE24-T",
        "BEE230-T",
        "BEE24ST",
        "BEE230ST",
        "BE24-T",
        "BLE24-T",
        "BLE230-T",
        "FST-24-3N",
        "FST-230-3N",
        "FSR-24-3N",
        "FSR-230-3N",
    },
)


def belimo_code_is_issued(code: str | None) -> bool:
    """False only for articles this catalog used to invent.

    Other tokens (``CM230-L/R``, a hand-typed real variant) stay allowed.
    """
    return normalize_belimo_code(code or "") not in BELIMO_NOT_ISSUED


def compose_belimo_article(
    family: str,
    *,
    voltage: str,
    modulating: bool,
    aux: bool,
    thermal: bool = False,
) -> str | None:
    """Belimo article for one Hoocon edition, or None when that article is not made.

    The map is the nomenclature. Combinations Belimo does not sell
    (Q-series 230 V, ``…-SR-S`` on LM/NM/SM/Q, ``LF…-RS``, smoke ``-T``,
    ``NF…-S`` without the ``2``) are absent and return None.

    Shared by ТТХ inference and the curated «Аналоги» generators so both
    always print the same article for the same edition.

    Args:
        family: Belimo series letters (``LM``, ``NMQ``, ``LF``, ``BFN``, ``BEN`` …).
        voltage: ``24`` or ``230``.
        modulating: Hoocon ``-A/-AS`` (0…10 В) edition.
        aux: Hoocon edition with auxiliary switches (``-DS/-AS/S``).
        thermal: Hoocon thermal edition (``DST`` / ``ST``).
    """
    if voltage not in {"24", "230"}:
        return None
    return BELIMO_CATALOG.get((family, voltage, modulating, aux, thermal))


def _belimo_family_of(code: str) -> str | None:
    """Belimo series letters of an article (``BFL24-T`` → ``BFL``)."""
    match = _FAMILY_PREFIX.match(normalize_belimo_code(code))
    return match.group(1) if match else None


def hoocon_torque_nm(sku_code: str | None) -> int | None:
    """Rated torque from a Hoocon actuator article (``DA16MU24-D`` → 16, ``HVD24S-3F`` → 3)."""
    match = _HOOCON_NM.match((sku_code or "").strip())
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def belimo_code_is_direct_for_sku(code: str | None, sku_code: str | None) -> bool:
    """Whether a Belimo article is a direct analog of this Hoocon edition.

    Direct means the customer can swap the Belimo for our actuator as is:
    the Belimo is not stronger (its damper area ≤ Hoocon's, area = Нм / 10),
    and an edition with auxiliary switches maps to a Belimo that has them
    (``…-S`` or the fire / smoke built-in 2× SPDT). Unknown articles or
    non-actuator SKUs are not judged (True); kits and ball valves never
    have a direct analog.
    """
    if sku_code_takes_no_analogs(sku_code):
        return False
    family = _belimo_family_of(code or "")
    if family is None:
        return True
    # QX is capacitor return. A fast non-fail-safe article (LMQ…GMQ) can
    # still pass the area check; it is not a direct analog of this SKU.
    purpose = detect_purpose(category_slug="", sku_code=sku_code or "")
    if purpose == "electronic_failsafe":
        allowed = {name for name, _area in BELIMO_FAMILY_AREA["electronic_failsafe"]}
        if family not in allowed:
            return False
    nm = hoocon_torque_nm(sku_code)
    if nm is not None and _FAMILY_AREA[family] > round(nm / 10, 2):
        return False
    variant = parse_sku_variant(sku_code or "")
    if _resolve_aux_switch(variant.aux_switch, sku_code or "") and family not in _BUILTIN_AUX_FAMILIES:
        return bool(re.search(r"-S\d?$", normalize_belimo_code(code or "")))
    return True


def detect_purpose(*, category_slug: str, sku_code: str) -> Purpose:
    """Infer actuator purpose from category slug and SKU code."""
    slug = (category_slug or "").casefold()
    code = (sku_code or "").casefold()
    if sku_code_takes_no_analogs(code):
        return "valve"
    # HVD-…F: spring-return smoke/fire compact (same Belimo BFL/BLF class as SA..FU).
    # Must win over category ``…dymoudalen…`` which also hosts SA..MU (no spring).
    if re.search(r"(?i)^hvd\d.*-\d+f(?:$|[^a-z0-9])", code):
        return "fire_spring"
    # HVD-QX — capacitor return. Not the fast non-fail-safe Q series.
    if re.search(r"(?i)^hvd\d.*-\d+qx(?:$|[^a-z0-9])", code):
        return "electronic_failsafe"
    # HVD-Q — fast non-spring air (not fire).
    if re.search(r"(?i)^hvd\d.*-\d+q(?:$|[^a-z0-9])", code):
        return "fast"
    if re.search(r"(?i)^hvd\d", code):
        return "air_no_spring"
    # HVA: suffix decides spring / speed / capacitor regardless of category.
    if hva := parse_hva_code(sku_code):
        if hva.suffix == "p":
            return "air_spring"
        if hva.suffix == "qx":
            return "electronic_failsafe"
        return "fast" if hva.suffix in {"q", "uq"} else "air_no_spring"
    for fragment, purpose in _PURPOSE_BY_CATEGORY:
        if fragment in slug:
            return purpose
    if code.startswith("sa") and "fu" in code:
        return "fire_spring"
    if "mqu" in code or code.startswith("hva"):
        return "fast"
    # DA..MU / SA..MU — no spring return (not HVD).
    if re.search(r"(?i)(?:^|[^a-z])(?:da|sa)\d*mu", code) or (
        "mu" in code and "fu" not in code and not code.startswith("hvd")
    ):
        return "air_no_spring"
    if "fu" in code:
        return "air_spring"
    if code.startswith("bv") or "8100" in code:
        return "valve"
    return "unknown"


def analogs_plain_text_for_sku(sku: SKU) -> str:
    """Edition-scoped analogs plain text (SKU or product tab)."""
    from catalog.sku_access import sku_section_text

    if sku_takes_no_analogs(sku):
        return ""
    # Empty SKU analogs_text is intentional (do not re-inherit product block).
    raw = sku_section_text(sku, "analogs_text")
    if not raw.strip():
        return ""
    filtered = _analogs_text_scoped(raw, sku)
    return _drop_belimo_lines_for_thermal(filtered, sku_code_is_thermal(sku.sku_code))


def _analogs_text_scoped(raw: str, sku: SKU) -> str:
    """Filter analogs by edition / control / aux (shared resolution + PDP base)."""
    filtered = filter_analogs_for_sku(raw, sku.sku_code)
    variant = parse_sku_variant(sku.sku_code)
    if _sku_uses_ds_as_control_editions(sku.sku_code):
        filtered = _drop_belimo_lines_for_control(filtered, variant.control)
    aux = _resolve_aux_switch(variant.aux_switch, sku.sku_code)
    filtered = _drop_belimo_lines_for_aux(filtered, aux)
    filtered = _drop_belimo_lines_not_direct(filtered, sku.sku_code)
    return _drop_unissued_belimo_lines(filtered)


def _drop_unissued_belimo_lines(text: str) -> str:
    """Drop bullets whose Belimo token is one this project used to invent."""
    if not text.strip():
        return text
    out: list[str] = []
    for line in text.splitlines():
        codes = extract_belimo_codes_from_text(line)
        if codes and not any(belimo_code_is_issued(code) for code in codes):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _drop_belimo_lines_not_direct(text: str, sku_code: str) -> str:
    """Drop Belimo bullets that are only a «closest class», not a direct analog."""
    if not text.strip():
        return text
    out: list[str] = []
    for line in text.splitlines():
        codes = extract_belimo_codes_from_text(line)
        if codes and not any(belimo_code_is_direct_for_sku(c, sku_code) for c in codes):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _drop_belimo_lines_for_thermal(text: str, thermal_sku: bool) -> str:
    """Keep Belimo bullets that match thermal vs non-thermal SKU edition."""
    if not text.strip():
        return text
    out: list[str] = []
    for line in text.splitlines():
        codes = extract_belimo_codes_from_text(line)
        if codes:
            if thermal_sku and not any(belimo_code_is_thermal(c) for c in codes):
                continue
            if not thermal_sku and all(belimo_code_is_thermal(c) for c in codes):
                continue
        out.append(line)
    return "\n".join(out).strip()


def _drop_belimo_lines_for_control(text: str, control: str | None) -> str:
    """Remove Belimo bullet lines that contradict SKU control (shared DS/AS lists)."""
    if not control or not text.strip():
        return text
    out: list[str] = []
    for line in text.splitlines():
        codes = extract_belimo_codes_from_text(line)
        if codes and not any(belimo_code_matches_control(c, control) for c in codes):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _drop_belimo_lines_for_aux(text: str, aux_switch: bool | None) -> str:
    """Drop the mismatched side of Belimo BASE / BASE-S bullet pairs."""
    if aux_switch is None or not text.strip():
        return text
    codes = extract_belimo_codes_from_text(text)
    keep = set(_filter_codes_by_aux(codes, aux_switch))
    if not codes or keep == set(codes):
        return text
    out: list[str] = []
    for line in text.splitlines():
        line_codes = extract_belimo_codes_from_text(line)
        if line_codes and not any(code in keep for code in line_codes):
            continue
        out.append(line)
    return "\n".join(out).strip()


def belimo_code_is_modulating(code: str | None) -> bool:
    """True when a Belimo article is a modulating (``-SR``) edition.

    Belimo marks proportional control with ``-SR`` (e.g. ``LM24A-SR``,
    ``LM24A-SR-S``, ``NM24A-SR-20``). Open/close articles (``LM24A-S``,
    ``CM230-L/R``) do not include that token.
    """
    return bool(re.search(r"-SR(?:-|$)", normalize_belimo_code(code or "")))


def belimo_code_is_open_close(code: str | None) -> bool:
    """True for clear open/close Belimo articles (not proportional ``-SR``).

    Matches ``CM230-L/R``, ``TMC230A`` / ``TMC230A-S``, and ``LM24A`` /
    ``LM24A-S``. Does **not** match spring-return ``LF24-RS`` / ``LF24-S``
    (``-RS`` / bare ``-S`` on LF/NF), which appear on both control sides in
    Tilda cards.
    """
    normalized = normalize_belimo_code(code or "")
    if not normalized or belimo_code_is_modulating(normalized):
        return False
    if re.search(r"-L(?:/R)?$|-R$", normalized):
        return True
    # Non-spring LM/NM/SM/GM/TMC/LMC (± aux ``-S``), no ``-SR``.
    return bool(re.search(r"^(?:LM|NM|SM|GM|TMC|LMC)\d+A(?:-S\d?)?$", normalized))


def belimo_code_matches_control(code: str | None, control: str | None) -> bool:
    """Whether a Belimo article fits Hoocon control (``on_off`` / ``modulating``).

    Shared Tilda blocks often list one Belimo line under ``…-DS/…-AS``. We only
    reject unambiguous mismatches: modulating SKU + open/close article, or
    on/off SKU + ``-SR`` article. Ambiguous spring codes (``LF24-RS``) are kept.
    """
    if not control or not (code or "").strip():
        return True
    if control == "modulating":
        return not belimo_code_is_open_close(code)
    if control in {"on_off", "3_point"}:
        return not belimo_code_is_modulating(code)
    return True


def _sku_uses_ds_as_control_editions(sku_code: str) -> bool:
    """True for articles with Tilda ``-A/-AS`` / ``-D/-DS`` control suffixes."""
    from catalog.etl.html_text import _compact_sku_token, _sku_control_suffix

    suf = _sku_control_suffix(_compact_sku_token(sku_code))
    return suf in {"a", "as", "d", "ds", "dst"}


def belimo_article_for_sku(sku: SKU) -> str | None:
    """Belimo article on the public card (manual ``SKU.analog_belimo_code``)."""
    if sku_takes_no_analogs(sku):
        return None
    code = (sku.analog_belimo_code or "").strip()
    return code or None


def belimo_codes_for_sku(sku: SKU) -> list[str]:
    """Belimo articles for catalog facets / filters (one manual code per SKU)."""
    code = belimo_article_for_sku(sku)
    return [code] if code else []


def _resolve_aux_switch(parsed: bool | None, sku_code: str) -> bool | None:
    """Edition aux flag from SKU code when ``parse_sku_variant`` left it None."""
    if parsed is not None:
        return parsed
    code = (sku_code or "").casefold()
    # HVD24S-20 / HVA24S-5Q — «S» before torque means aux switches.
    if re.search(r"(?:hvd|hva)\d+s", code):
        return True
    if re.search(r"(?:hvd|hva)\d", code):
        return False
    return None


def _filter_codes_by_aux(codes: list[str], aux_switch: bool | None) -> list[str]:
    """Drop the mismatched side of BASE / BASE-S pairs only.

    Unrelated articles (``LF24-S`` + ``LF24-RS``) are kept together.
    Lone ``…-S`` without a bare pair is left as-is here; non-aux editions
    are normalized later by :func:`_strip_lone_aux_suffix`.
    """
    if aux_switch is None or len(codes) <= 1:
        return codes
    drop: set[str] = set()
    for code in codes:
        if not re.search(r"-S\d?$", code, re.I):
            continue
        base = re.sub(r"-S\d?$", "", code, flags=re.I)
        if base not in codes:
            continue
        if aux_switch:
            drop.add(base)
        else:
            drop.add(code)
    if not drop:
        return codes
    return [code for code in codes if code not in drop]


def _strip_lone_aux_suffix(codes: list[str], aux_switch: bool | None) -> list[str]:
    """For non-aux SKUs, strip trailing ``-S`` when the card listed only the aux article.

    Shared D/DS analog blocks often list a single ``LM24A-S``; without a bare
    ``LM24A`` pair, :func:`_filter_codes_by_aux` cannot drop the mismatch.
    """
    if aux_switch is not False or not codes:
        return codes
    out: list[str] = []
    for code in codes:
        if re.search(r"-S\d?$", code, re.I):
            base = re.sub(r"-S\d?$", "", code, flags=re.I)
            out.append(base if base else code)
        else:
            out.append(code)
    # Dedupe while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for code in out:
        if code in seen:
            continue
        seen.add(code)
        unique.append(code)
    return unique


def _filter_codes_by_control(codes: list[str], control: str | None) -> list[str]:
    """Keep Belimo articles that match Hoocon ``on_off`` / ``modulating``."""
    if not control or not codes:
        return codes
    return [code for code in codes if belimo_code_matches_control(code, control)]


def belimo_code_is_thermal(code: str | None) -> bool:
    """True when a Belimo article is a thermal edition (``-T`` / ``FST`` / ``-FST``).

    Args:
        code: Belimo article (e.g. ``BF24-T``, ``BF24-FST``).

    Returns:
        True for a trailing ``-T``, a leading ``FST`` series, or ``-FST``.
        ``BEE24-ST`` is a connector plug, not a thermal sensor.
        Mid-string ``-T-`` (e.g. ``X-T-Y``) is not thermal.
    """
    return bool(_THERMAL_BELIMO_TOKEN.search(normalize_belimo_code(code or "").casefold()))


def primary_belimo_code_for_sku(sku: SKU) -> str | None:
    """Same as :func:`belimo_article_for_sku` (manual field)."""
    return belimo_article_for_sku(sku)


_ANALOG_BULLET = re.compile(r"^\s*[–—\-•*]")
# A bare edition header left after its bullets are gone:
# ``CODE…:`` or ``CODE…: (примечание)``.
_ORPHAN_EDITION_HEADER = re.compile(r"^.*:\s*(\([^()]*\))?\s*$")


def _drop_unverified_analog_lines(text: str) -> str:
    """Remove analog-candidate bullets and headers left without a pair.

    A bullet in the analogs tab names one foreign article as a stand-in for
    this edition. No stored bullet is a datasheet-confirmed pair, so the tab
    keeps only the selection guidance. A block reduced to its bare edition
    header (``SA15MU24-DST (24 В, …):``, ``HVD24ST-5F: (с термодатчиком)``)
    is dropped with it.
    """
    if not text.strip():
        return text
    kept: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line for line in block.splitlines() if not _ANALOG_BULLET.match(line)]
        if not lines:
            continue
        if len(lines) == 1 and _ORPHAN_EDITION_HEADER.match(lines[0].rstrip()):
            continue
        kept.append("\n".join(lines))
    return "\n\n".join(kept).strip()


def _verified_analog_lines(sku: SKU) -> list[str]:
    """Bullets for the manually verified Belimo code on the card."""
    code = belimo_article_for_sku(sku)
    if not code:
        return []
    return [f"– Belimo {code}"]


def analogs_text_for_card(sku: SKU) -> str:
    """Analogs tab: manual Belimo code first, then selection guidance.

    Unverified bullets from old copy are dropped; only ``analog_belimo_code``
    is shown as a confirmed replacement.
    """
    guidance = _drop_unverified_analog_lines(analogs_plain_text_for_sku(sku))
    lines = _verified_analog_lines(sku)
    if not lines:
        return guidance
    head = "Подтверждённые замены (сверено с даташитом):\n" + "\n".join(lines)
    return f"{head}\n\n{guidance}" if guidance else head


def _infer_for_sku(sku: SKU, *, voltage: str | None) -> list[str]:
    """Build inference inputs from EAV / variant and call ``infer_belimo_codes``."""
    from catalog.sku_access import sku_category_slug_or_empty

    category_slug = sku_category_slug_or_empty(sku)
    purpose = detect_purpose(category_slug=category_slug, sku_code=sku.sku_code)
    if purpose in {"valve", "unknown"}:
        return []

    attrs = _sku_attr_map(sku)
    variant = parse_sku_variant(sku.sku_code)
    volt = voltage or variant.voltage or _voltage_from_attr(attrs.get("voltage", ""))
    control = variant.control or _control_from_attr(attrs.get("control", ""))
    # The edition suffix (D/DS, A/AS, HVD…S) is authoritative; EAV only fills gaps.
    edition_aux = _resolve_aux_switch(variant.aux_switch, sku.sku_code)
    if edition_aux is not None:
        aux = 1 if edition_aux else 0
    else:
        aux = _aux_spdt_from_attr(attrs.get("aux-switch", ""), sku_code=sku.sku_code) or 0
    moment = _parse_float(attrs.get("moment", ""))
    if moment is None:
        moment = hoocon_torque_nm(sku.sku_code)
    area = _parse_area(attrs.get("damper-area", ""))
    thermal = sku_code_is_thermal(sku.sku_code)
    return infer_belimo_codes(
        purpose=purpose,
        moment_nm=moment,
        voltage=volt,
        control=control,
        aux_spdt=aux or 0,
        thermal=thermal,
        damper_area_m2=area,
    )


def _sku_attr_map(sku: SKU) -> dict[str, str]:
    """Slug → value for inference (prefetched when available).

    First occurrence of each slug wins (keeps the earlier AttributeValue).
    Opaque Tilda ``attr-*`` slugs are aliased to canonical keys via names below.
    """
    from catalog.sku_access import sku_attribute_values

    values = sku_attribute_values(sku)
    out: dict[str, str] = {}
    for av in values:
        slug = (av.attribute.slug or "").casefold()
        if not slug or slug in out:
            continue
        out[slug] = str(av.value or "")
    # Alias opaque Tilda slugs by attribute name when needed.
    for av in values:
        name = (av.attribute.name or "").casefold()
        if "крутящий момент" in name or name == "момент":
            out.setdefault("moment", str(av.value or ""))
        elif "напряжен" in name and "диапазон" not in name:
            out.setdefault("voltage", str(av.value or ""))
        elif name == "управление" or name.startswith("управление "):
            out.setdefault("control", str(av.value or ""))
        elif "вспомогательн" in name:
            out.setdefault("aux-switch", str(av.value or ""))
        elif "площад" in name:
            out.setdefault("damper-area", str(av.value or ""))
    return out


def _voltage_from_attr(value: str) -> str | None:
    if _HAS_230.search(value or ""):
        return "230"
    if _HAS_24.search(value or ""):
        return "24"
    return None


def _control_from_attr(value: str) -> str | None:
    low = (value or "").casefold()
    if "пропорционал" in low or "модулир" in low:
        return "modulating"
    if "открыто" in low or "2-" in low or "3-" in low or "позицион" in low:
        return "on_off"
    return None


def _aux_spdt_from_attr(value: str, *, sku_code: str) -> int | None:
    """Parse SPDT count from EAV without importing facets (avoid cycles)."""
    low = (value or "").casefold().strip()
    if not low or low in {"нет", "no", "0", "-", "—", "–"}:
        return 0
    if "spdt-2" in low or re.search(r"\b2\b", low):
        return 2
    if "spdt-1" in low or re.search(r"\b1\b", low) or "да" in low:
        return 1
    # Edition suffix AS/S often means two switches on modulating air SKUs.
    code = (sku_code or "").casefold()
    if re.search(r"-as(?:$|[^a-z])", code) or code.endswith("-as"):
        return 2
    if re.search(r"-ds(?:$|[^a-z])", code) or code.endswith(("-ds", "-s")):
        return 1
    return None


def _parse_float(value: str) -> float | None:
    match = _MOMENT_NUM.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _parse_area(value: str) -> float | None:
    match = _AREA_NUM.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None
