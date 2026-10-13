"""Belimo analog codes from card «Аналоги» text or ТТХ heuristics.

Used by the catalog «Аналоги» facet and ``SKU.analog_belimo_code`` backfill.
Prefer explicit Belimo lines in copy; otherwise infer a typical Belimo article
from purpose (category), damper torque/area band, voltage, control, aux SPDT.
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
# Belimo thermal: ``BF24-T``, ``BF24-FST``, ``FST-230-3N``, smoke ``BEE24ST``.
_THERMAL_BELIMO_TOKEN = re.compile(
    r"(?:^|-)fst(?:-|$)|fst$|st$|-t$",
)

# Belimo recommended max damper area per family, м² — EU datasheets / selection tools.
# Primary criterion: the customer picks a Belimo actuator by the damper it must move.
# Fire: motor/spring torque differs; area is still the selection key.
# Smoke BEN and BLE share the 1.5 m² area class; BEN is the primary family.
BELIMO_FAMILY_AREA: dict[str, tuple[tuple[str, float], ...]] = {
    "air_no_spring": (("TMC", 0.2), ("LM", 0.5), ("NM", 1.0), ("SM", 2.0), ("GM", 4.0)),
    "air_spring": (("TF", 0.25), ("LF", 0.4), ("NF", 1.0), ("SF", 2.0)),
    "fire_spring": (("BFL", 0.4), ("BLF", 0.5), ("BFN", 0.8), ("BF", 1.5)),
    "fast": (("LMQ", 0.4), ("NMQ", 0.8), ("SMQ", 1.6), ("GMQ", 4.0)),
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


def compose_belimo_article(
    family: str,
    *,
    voltage: str,
    modulating: bool,
    aux: bool,
    thermal: bool = False,
) -> str | None:
    """Belimo article for one Hoocon edition, or None when Belimo has no direct analog.

    Shared by ТТХ inference and the curated «Аналоги» generators so both
    always print the same article for the same edition.

    Args:
        family: Belimo series letters (``LM``, ``NMQ``, ``LF``, ``BFN``, ``BEN`` …).
        voltage: ``24`` or ``230``.
        modulating: Hoocon ``-A/-AS`` (0…10 В) edition.
        aux: Hoocon edition with auxiliary switches (``-DS/-AS/S``).
        thermal: Hoocon thermal edition (``DST`` / ``ST``).
    """
    if family in _BUILTIN_AUX_FAMILIES:
        # Fire / smoke: on/off only, 2× SPDT built in, optional thermal.
        if modulating:
            return None
        if family == "BEE":
            return f"BEE{voltage}{'ST' if thermal else ''}"
        return f"{family}{voltage}{'-T' if thermal else ''}"
    if family == "TF":
        # TF24 / TF24-S; no proportional edition in the card range.
        if modulating:
            return None
        return f"TF{voltage}{'-S' if aux else ''}"
    if family == "LF":
        # LF24 / LF24-S / LF24-RS (proportional, no auxiliary switches).
        if modulating:
            return None if aux else f"LF{voltage}-RS"
        return f"LF{voltage}{'-S' if aux else ''}"
    if family == "TMC" and modulating and aux:
        # Belimo ships aux as add-on S1A, not a factory ``…-SR-S``.
        return None
    # LM/NM/SM/GM/TMC, LMQ…GMQ, NF/SF — modern ``A`` generation.
    code = f"{family}{voltage}A"
    if modulating:
        code += "-SR"
    if aux:
        code += "-S"
    return code


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
    # HVD-Q / HVD-QX — fast non-spring air (not fire).
    if re.search(r"(?i)^hvd\d.*-\d+qx?(?:$|[^a-z0-9])", code):
        return "fast"
    if re.search(r"(?i)^hvd\d", code):
        return "air_no_spring"
    # HVA: suffix decides spring / speed regardless of category (QX lives in «отказоустойчивые»).
    if hva := parse_hva_code(sku_code):
        if hva.suffix == "p":
            return "air_spring"
        return "fast" if hva.suffix in {"q", "uq", "qx"} else "air_no_spring"
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
    return _drop_belimo_lines_not_direct(filtered, sku.sku_code)


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


def belimo_codes_for_sku(sku: SKU) -> list[str]:
    """Resolve Belimo codes for a SKU: card text first, else ТТХ inference.

    Card text wins only when codes match the SKU control mode. Combined
    ``-DS/-AS`` analog blocks often list an on/off Belimo (e.g. ``CM230-L/R``);
    modulating editions then fall through to inference (``…-SR``).

    Args:
        sku: Catalog SKU (product + category + EAV used when inferring).

    Returns:
        Ordered unique Belimo article codes.
    """
    if sku_takes_no_analogs(sku):
        return []
    variant = parse_sku_variant(sku.sku_code)
    voltage = variant.voltage
    control = variant.control
    apply_control = _sku_uses_ds_as_control_editions(sku.sku_code)
    from catalog.sku_access import sku_section_text

    raw = sku_section_text(sku, "analogs_text")
    text = _analogs_text_scoped(raw, sku) if raw.strip() else ""
    from_text = extract_belimo_codes_from_text(text, voltage=voltage)
    if from_text:
        aux = _resolve_aux_switch(variant.aux_switch, sku.sku_code)
        filtered = _strip_lone_aux_suffix(_filter_codes_by_aux(from_text, aux), aux)
        if apply_control:
            filtered = _filter_codes_by_control(filtered, control)
        if sku_code_is_thermal(sku.sku_code):
            thermal_only = [c for c in filtered if belimo_code_is_thermal(c)]
            if thermal_only:
                filtered = thermal_only
            # else keep card codes for facet; primary_belimo_code_for_sku
            # still refuses a non-thermal primary.
        else:
            filtered = [c for c in filtered if not belimo_code_is_thermal(c)]
        if filtered:
            return filtered

    stored = (sku.analog_belimo_code or "").strip()
    if stored:
        code = normalize_belimo_code(stored)
        thermal_sku = sku_code_is_thermal(sku.sku_code)
        thermal_code = belimo_code_is_thermal(code)
        # Stale fill: thermal Belimo on plain DS (or reverse) must not block inference.
        if thermal_sku != thermal_code or not belimo_code_is_direct_for_sku(code, sku.sku_code):
            pass
        elif not apply_control or belimo_code_matches_control(code, control):
            aux = _resolve_aux_switch(variant.aux_switch, sku.sku_code)
            filtered = _strip_lone_aux_suffix(_filter_codes_by_aux([code], aux), aux)
            if filtered:
                return filtered

    return _infer_for_sku(sku, voltage=voltage)


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
    """True when a Belimo article is a thermal edition (``FST`` / ``ST`` / ``-T``).

    Args:
        code: Belimo article (e.g. ``BF24-T``, ``FST-230-3N``, ``BEE24ST``).

    Returns:
        True for ``FST…`` / ``…ST`` / ``…-T`` / ``…-FST`` thermal markers.
        Mid-string ``-T-`` (e.g. ``X-T-Y``) is not thermal.
    """
    return bool(_THERMAL_BELIMO_TOKEN.search(normalize_belimo_code(code or "").casefold()))


def primary_belimo_code_for_sku(sku: SKU) -> str | None:
    """First Belimo code for ``SKU.analog_belimo_code`` persistence.

    Thermal editions (``DST`` / ``-T`` suffix on the Hoocon article) must map to a
    thermal Belimo code (``FST`` / ``-T``). If none is present among resolved
    codes, return ``None`` rather than a non-thermal fallback.
    """
    codes = belimo_codes_for_sku(sku)
    if not codes:
        return None
    if not sku_code_is_thermal(sku.sku_code):
        return codes[0]
    for code in codes:
        if belimo_code_is_thermal(code):
            return code
    return None


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
