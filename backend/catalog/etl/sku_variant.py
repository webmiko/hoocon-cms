"""Detect SKU electrical variant from ``sku_code`` and filter mixed copy.

Tilda product pages describe the whole series (24 В + 230 В, D/DS + A/AS).
Each catalog SKU must keep only the characteristics that apply to that edition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_VOLTAGE_230 = re.compile(
    r"(?:^|[^0-9])230(?:[^0-9]|$)|100\s*\.\.\.\s*240|100\s*-\s*240|100…240",
    re.I,
)
_VOLTAGE_24 = re.compile(r"(?:^|[^0-9])24(?:[^0-9]|$)", re.I)
_MODEL_HEADER = re.compile(
    r"^(?P<code>[A-Z]{1,6}\d{0,3}[A-Z]{0,4})(?P<body>[A-Z0-9/.\-]*)\s*:?\s*$",
    re.I,
)
_BULLET_24 = re.compile(r"^\s*[–—\-•]?\s*24\s*В\b", re.I)
_BULLET_230 = re.compile(
    r"^\s*[–—\-•]?\s*(?:230\s*В\b|100\s*\.\.\.\s*240|100\s*-\s*240)",
    re.I,
)
_BOTH_VOLTAGES_SENTENCE = re.compile(
    r"(?i)работают от\s+AC/?DC\s*24\s*V?\s*или\s+AC\s*100",
)
_AUX_LINE = re.compile(r"(?i)вспомогательн\w*\s+переключател")
_MODULATING_LINE = re.compile(
    r"(?i)плавн\w+\s+регулир|пропорциональн\w*|модулир\w*|"
    r"суффиксом\s+-?A/?AS|0\s*−\s*10\s*V",
)
_ON_OFF_ONLY = re.compile(r"(?i)2-позицион|открыто\s*/\s*закрыто")

# Series templates from docs: DA3FU24/230-D/DS, DA3FU24(230)-D(S)
_DUAL_VOLTAGE_CODE = re.compile(
    r"(?P<pre>\b[A-Za-z]{1,6}\d{0,3}[A-Za-z]{0,6})24\s*(?:/\s*230|\(\s*230\s*\))",
    re.I,
)
_DUAL_VOLTAGE_BARE = re.compile(r"\b24\s*/\s*230\b")
_SUFFIX_D_DS = re.compile(r"-D\s*/\s*DS\b|-D\s*\(\s*S\s*\)", re.I)
_SUFFIX_A_AS = re.compile(r"-A\s*/\s*AS\b|-A\s*\(\s*S\s*\)", re.I)
_SUFFIX_DS_T = re.compile(r"-DS\s*\(\s*T\s*\)|-DS\s*/\s*T\b", re.I)


@dataclass(frozen=True, slots=True)
class SkuVariant:
    """Electrical / control variant inferred from SKU code."""

    voltage: str | None  # "24" | "230" | None
    control: str | None  # "on_off" | "modulating" | None
    aux_switch: bool | None
    code: str


def parse_sku_variant(sku_code: str) -> SkuVariant:
    """Infer voltage / control / aux-switch from a Tilda edition SKU code.

    Args:
        sku_code: e.g. ``da3fu230-d``, ``da10fu24-as``, ``8100-bv215a``.

    Returns:
        Parsed variant (fields may be None when code is ambiguous).
    """
    code = (sku_code or "").strip().lower().replace(" ", "")
    voltage: str | None = None
    if re.search(r"(?:^|[^0-9])230(?:[^0-9]|$)", code):
        voltage = "230"
    elif re.search(r"(?:fu|mu|sa|hvd)24|(?:^|[^0-9])24(?:-|$)", code):
        voltage = "24"
    elif "24" in code and "230" not in code:
        voltage = "24"

    control: str | None = None
    aux: bool | None = None
    # Suffixes are hyphen-prefixed edition tags strictly at the code end.
    # ``-dst`` before ``-ds`` (thermal ON/OFF with aux).
    if code.endswith("-as"):
        control = "modulating"
        aux = True
    elif code.endswith("-dst"):
        control = "on_off"
        aux = True
    elif code.endswith("-ds"):
        control = "on_off"
        aux = True
    elif code.endswith("-a"):
        control = "modulating"
        aux = False
    elif code.endswith("-d"):
        control = "on_off"
        aux = False

    return SkuVariant(voltage=voltage, control=control, aux_switch=aux, code=code)


def _header_voltage(header: str) -> str | None:
    """Return ``24`` / ``230`` if a model header encodes a single voltage.

    Dual masks like ``DA3FU24/230`` or ``DA3FU24(230)`` return None so the
    line is kept and rewritten to the SKU edition.
    """
    if re.search(r"24\s*(?:/|\()\s*230", header, re.I):
        return None
    if re.search(r"230|100\s*\.\.\.\s*240|100\s*-\s*240", header, re.I):
        return "230"
    if re.search(r"(?:FU|MU|SA|HVD|HVA)?24(?:-|/|$|\s)", header, re.I):
        return "24"
    if re.search(r"\b24\b", header) and "230" not in header:
        return "24"
    return None


def _header_control(header: str) -> str | None:
    """Return control family from a model header like ``DA10FU24-A/AS:``.

    Dual masks ``-D/DS`` / ``-A/AS`` return None (kept + rewritten).
    """
    upper = header.upper()
    if re.search(r"-D\s*/\s*DS|-D\s*\(\s*S\s*\)", upper):
        return None
    if re.search(r"-A\s*/\s*AS|-A\s*\(\s*S\s*\)", upper):
        return None
    if re.search(r"-A(?:S)?(?:\s*:|$)", upper) and "D/DS" not in upper:
        return "modulating"
    if re.search(r"-D(?:S)?(?:\s*:|$)", upper):
        return "on_off"
    return None


def _is_model_header(line: str) -> bool:
    """True for edition headers such as ``DA3FU230-D/DS:``."""
    bare = line.strip().rstrip(":")
    if len(bare) < 5 or len(bare) > 40:
        return False
    if " " in bare and "/" not in bare:
        return False
    return bool(re.match(r"^[A-Za-z]{2,}\d", bare))


def rewrite_series_tokens_for_variant(text: str, variant: SkuVariant) -> str:
    """Replace series templates with the concrete SKU edition tokens.

    Per https://hoocon.ru/statyi/tpost/4uicugaoh1-spetsifikatsiya-modelnogo-ryada-privodov
    ``DA3FU24(230)-D(S)`` is a family mask; a card for ``da3fu230-d`` must
    show ``DA3FU230-D``, not ``DA3FU24/230-D/DS``.

    Args:
        text: One line or a full description.
        variant: Parsed SKU edition.

    Returns:
        Text with dual voltage / dual suffix masks narrowed.
    """
    if not text:
        return text

    def _volt_repl(match: re.Match[str]) -> str:
        pre = match.group("pre")
        if variant.voltage == "230":
            return f"{pre}230"
        if variant.voltage == "24":
            return f"{pre}24"
        return match.group(0)

    out = _DUAL_VOLTAGE_CODE.sub(_volt_repl, text)
    if variant.voltage == "230":
        out = _DUAL_VOLTAGE_BARE.sub("230", out)
    elif variant.voltage == "24":
        out = _DUAL_VOLTAGE_BARE.sub("24", out)

    if variant.control == "on_off":
        if variant.aux_switch is True:
            out = _SUFFIX_D_DS.sub("-DS", out)
        elif variant.aux_switch is False:
            out = _SUFFIX_D_DS.sub("-D", out)
    elif variant.control == "modulating":
        if variant.aux_switch is True:
            out = _SUFFIX_A_AS.sub("-AS", out)
        elif variant.aux_switch is False:
            out = _SUFFIX_A_AS.sub("-A", out)

    return out


def filter_description_for_variant(text: str, variant: SkuVariant) -> str:
    """Strip other-voltage / other-control blocks from a series description.

    Also rewrites ``24/230`` and ``D/DS`` series masks to the SKU edition
    (see rewrite_series_tokens_for_variant).

    Edition blocks start at model headers (``DA3FU24-D/DS:``). While a
    non-matching header is active, all following lines are dropped until the
    next model header — including nested section titles like «Характеристики:».
    Put shared series copy (voltage ranges, marketing bullets) *before*
    edition blocks or under a matching header so it is not skipped.

    Args:
        text: Shared product-line description pasted onto a SKU.
        variant: Parsed edition of that SKU.

    Returns:
        Description scoped to the SKU variant.
    """
    if not text or not text.strip():
        return ""
    if variant.voltage is None and variant.control is None:
        return rewrite_series_tokens_for_variant(text.strip(), variant)

    lines = text.replace("\xa0", " ").splitlines()
    out: list[str] = []
    skipping = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if _is_model_header(stripped):
            hv = _header_voltage(stripped)
            hc = _header_control(stripped)
            drop = False
            if variant.voltage and hv and hv != variant.voltage:
                drop = True
            if variant.control and hc and hc != variant.control:
                drop = True
            skipping = drop
            if drop:
                continue
            header = rewrite_series_tokens_for_variant(stripped, variant)
            out.append(header if header.endswith(":") else f"{header}:")
            continue

        if skipping:
            # Stay skipped until the next model header (handled above). Generic
            # section titles like «Характеристики:» must not end the skip —
            # they belong to the dropped edition block.
            continue

        # Voltage-specific range bullets under «Диапазон напряжения».
        if variant.voltage == "24" and _BULLET_230.match(stripped):
            continue
        if variant.voltage == "230" and _BULLET_24.match(stripped):
            continue

        # Rewrite dual-voltage marketing sentence.
        if variant.voltage and _BOTH_VOLTAGES_SENTENCE.search(stripped):
            if variant.voltage == "24":
                out.append(
                    "– Работает от AC/DC 24 В (19,2−28,8 В), 50/60 Гц.",
                )
            else:
                out.append(
                    "– Работает от AC 100…240 В (85−250 В), 50/60 Гц.",
                )
            continue

        # Control-specific marketing bullets.
        if variant.control == "on_off" and _MODULATING_LINE.search(stripped):
            continue
        if variant.control == "modulating" and _ON_OFF_ONLY.search(stripped):
            if not re.search(r"(?i)плавн|пропорциональн|модулир", stripped):
                continue
        if variant.aux_switch is False and _AUX_LINE.search(stripped):
            # Drop «2 SPDT in DS/AS» lines for plain -D/-A editions.
            if "SPDT" in stripped.upper() or "DS" in stripped.upper() or "AS" in stripped.upper():
                continue

        out.append(rewrite_series_tokens_for_variant(line, variant))

    # Collapse leftover blank runs
    cleaned: list[str] = []
    for line in out:
        if not line.strip():
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        cleaned.append(line.strip())
    text_out = "\n".join(cleaned).strip()
    text_out = re.sub(r"\n{3,}", "\n\n", text_out)
    return text_out


def filter_attributes_for_variant(
    rows: list[dict[str, str]],
    variant: SkuVariant,
) -> list[dict[str, str]]:
    """Drop ТТХ rows that contradict the SKU voltage / control.

    Args:
        rows: Serialized attribute dicts with ``name`` / ``value``.
        variant: Parsed SKU variant.

    Returns:
        Filtered rows (new list).
    """
    result: list[dict[str, str]] = []
    for row in rows:
        name = (row.get("name") or "").casefold()
        slug = (row.get("slug") or "").casefold()
        value = (row.get("value") or "").strip()
        value_l = value.casefold()

        if variant.voltage == "24":
            if "напряжен" in name and ("230" in value_l or "100" in value_l):
                continue
        if variant.voltage == "230":
            if "напряжен" in name and re.search(r"(?:^|[^0-9])24(?:\s*в|$)", value_l):
                if "230" not in value_l and "100" not in value_l:
                    continue

        # Y/U modulating signals only for пропорциональное editions.
        if variant.control == "on_off" and (
            "управляющий сигнал" in name
            or "обратная связь" in name
            or name in {"сигнал управления", "сигнал обратной связи"}
        ):
            continue
        from catalog.etl.tech_copy import is_control_mode_attribute

        if variant.control == "on_off" and is_control_mode_attribute(name=name, slug=slug):
            if re.search(r"плавн|пропорциональн|модулир", value_l):
                continue
        if variant.control == "modulating" and is_control_mode_attribute(name=name, slug=slug):
            if ("открыто" in value_l or "2-/3-позицион" in value_l or "2/3-позицион" in value_l) and not re.search(
                r"плавн|пропорциональн|модулир",
                value_l,
            ):
                continue

        if variant.aux_switch is False and "вспомогательн" in name:
            if value_l in {"да", "yes", "есть"} or "spdt" in value_l:
                continue
        if variant.aux_switch is True and "вспомогательн" in name:
            if value_l in {"нет", "no", "без"}:
                continue

        result.append(row)
    return result


# Tilda gallery alts tag control type; series pages attach both A/AS and D/DS photos.
_IMAGE_MODULATING = re.compile(
    r"(?i)управлени[ея]\s+плавн|тип\w*\s+управления\s+плавн|"
    r"плавное\s+управлени|пропорциональн|модулир",
)
_IMAGE_ON_OFF = re.compile(
    r"(?i)управлени[ея]\s+открыто|тип\w*\s+управления\s+открыто|"
    r"открыто\s*/\s*закрыто",
)
_NM_IN_ALT = re.compile(r"(?i)(\d+)\s*нм")
_NM_FROM_SKU = re.compile(r"(?i)^(?:da|sa|hva|hvd|hvq)?(\d+)")
# SA fire/smoke: sibling DS↔DST photos share one product gallery.
_IMAGE_THERMAL = re.compile(
    r"(?i)термодатчик|термическ\w*\s+датчик|72\s*[℃°]|-?\s*72\s*c\b",
)
_ALT_SKU_IN_PARENS = re.compile(r"\(([a-z0-9._-]+)\)\s*$", re.IGNORECASE)
_SA_CODE = re.compile(r"(?i)^sa\d")
_THERMAL_SKU_SUFFIX = re.compile(r"(?i)dst$|-t$")


def sku_code_is_thermal(sku_code: str | None) -> bool:
    """True when the Hoocon article is a thermal edition (``DST`` / ``-T`` suffix).

    Args:
        sku_code: Hoocon SKU article (e.g. ``SA5FU24-DST``).

    Returns:
        True only when the code ends with ``DST`` or ``-T`` (case-insensitive).
    """
    return bool(_THERMAL_SKU_SUFFIX.search((sku_code or "").casefold()))


def torque_nm_from_sku_code(sku_code: str) -> int | None:
    """Extract leading torque (Нм) from a series SKU code, if present.

    Args:
        sku_code: e.g. ``da5fu24-d``, ``DA8MQU230-AS``.

    Returns:
        Integer Nm or None when the code has no leading series number.
    """
    code = (sku_code or "").strip().lower().replace(" ", "")
    match = _NM_FROM_SKU.match(code)
    if not match:
        return None
    return int(match.group(1))


def _image_thermal_role(alt: str) -> str:
    """Classify a gallery alt as ``thermal``, ``non_thermal``, or ``unknown``."""
    text = (alt or "").strip()
    if not text:
        return "unknown"
    if _IMAGE_THERMAL.search(text):
        return "thermal"
    paren = _ALT_SKU_IN_PARENS.search(text)
    if paren is not None:
        tagged = paren.group(1)
        if sku_code_is_thermal(tagged):
            return "thermal"
        # Explicit non-thermal edition tag in alt (…-ds), not bare series.
        if re.search(r"(?i)(?:-ds|-d)$", tagged) and not sku_code_is_thermal(tagged):
            return "non_thermal"
    # Descriptive area shot without thermal wording = non-DST body on SA cards.
    if re.search(r"(?i)площад", text) and not _IMAGE_THERMAL.search(text):
        return "non_thermal"
    return "unknown"


def filter_images_for_variant[T](images: list[T], variant: SkuVariant) -> list[T]:
    """Drop gallery photos whose alt tags the opposite control / thermal / Nm.

    Shared shots (монтаж, hero without control wording) are kept. Wrong-torque
    alts from a sibling series (e.g. 3 Нм photo on DA5) are dropped when both
    sides expose an explicit Nm. SA DS/DST sibling photos tagged with
    термодатчик / opposite edition code are dropped.

    Args:
        images: ``ProductImage``-like objects with an ``alt`` attribute.
        variant: Parsed SKU variant (control / code).

    Returns:
        Filtered list preserving input order.
    """
    expected_nm = torque_nm_from_sku_code(variant.code)
    thermal_sku = sku_code_is_thermal(variant.code)
    is_sa = bool(_SA_CODE.match((variant.code or "").strip()))

    result: list[T] = []
    for image in images:
        alt = str(getattr(image, "alt", None) or "")
        if variant.control == "on_off" and _IMAGE_MODULATING.search(alt):
            continue
        if variant.control == "modulating" and _IMAGE_ON_OFF.search(alt):
            continue
        if expected_nm is not None:
            nm_match = _NM_IN_ALT.search(alt)
            if nm_match is not None and int(nm_match.group(1)) != expected_nm:
                continue
        if is_sa:
            role = _image_thermal_role(alt)
            if thermal_sku and role == "non_thermal":
                continue
            if not thermal_sku and role == "thermal":
                continue
        result.append(image)

    # When the gallery still mixes thermal + non-thermal roles, keep only the
    # edition that matches the SKU (covers alts without explicit keywords).
    if is_sa and len(result) > 1:
        roles = [_image_thermal_role(str(getattr(img, "alt", None) or "")) for img in result]
        if thermal_sku and "thermal" in roles:
            result = [img for img, role in zip(result, roles, strict=True) if role != "non_thermal"]
        elif not thermal_sku and "thermal" in roles:
            result = [img for img, role in zip(result, roles, strict=True) if role != "thermal"]

    return result
