"""Curated «Аналоги» for gap / empty cards — major brands only.

Policy (product / RF replacement framing): list only large, well-known makers,
especially those that left or suspended official business in RF:

Belimo, Siemens, Honeywell, Schneider Electric, Johnson Controls, Danfoss, Gruner.

Do **not** invent obscure OEM clones (Nanotek, Dastech, Lufberg, BVM, …).
Fill only when ``Product.analogs_text`` is empty (unless ``force=True``).
"""

from __future__ import annotations

import re
from typing import Any, Final

from catalog.etl.html_text import filter_analogs_for_sku
from catalog.etl.tech_copy import normalize_tech_copy
from catalog.models import SKU, Product

_FOOTNOTE = normalize_tech_copy(
    "При выборе аналога сверяйте крутящий момент, напряжение, "
    "тип управления, наличие вспомогательных переключателей "
    "и габариты монтажа. Точные артикулы ушедших из РФ брендов "
    "уточняйте по паспорту / шильдику заменяемого привода.",
)

# Belimo non-spring families by torque (EU).
_BELIMO_AIR: Final[dict[int, str]] = {
    5: "LM",
    8: "NM",
    10: "NM",
    16: "SM",
    20: "SM",
    24: "SM",
    32: "GM",
    40: "GM",
}

# Belimo quick-running (HVA-Q / DAMQU / HVD-Q).
_BELIMO_FAST: Final[dict[int, str]] = {
    5: "LMQ",
    8: "NMQ",
    10: "NMQ",
    20: "SMQ",
    40: "GMQ",
}

# Siemens OpenAir (on/off base; modulating → …61).
_SIEMENS_AIR: Final[dict[int, str]] = {
    5: "GDB",
    8: "GLB",
    10: "GLB",
    16: "GEB",
    20: "GEB",
    24: "GEB",
    32: "GIB",
    40: "GIB",
}


def _belimo_air(family: str, voltage: str, *, modulating: bool, aux: bool) -> str:
    code = f"{family}{voltage}A"
    if modulating:
        code += "-SR"
    if aux:
        code += "-S"
    return f"Belimo {code}"


def _siemens_air(prefix: str, voltage: str, *, modulating: bool, aux: bool) -> str:
    # OpenAir: GDB131.1E on/off 24 V; GDB161.1E modulating; 230 V → GCA / GEB / GIB.
    mid = "61" if modulating else "31"
    if voltage == "230":
        brand = {"GDB": "GCA", "GLB": "GCA", "GEB": "GEB", "GIB": "GIB"}.get(prefix, prefix)
        code = f"{brand}1{mid}.1E"
    else:
        code = f"{prefix}1{mid}.1E"
    if aux:
        code += "-S"
    return f"Siemens {code}"


def _honeywell_air(nm: int, voltage: str, *, modulating: bool, aux: bool) -> str:
    # Compact Honeywell MN / ML band used on existing HVD-20 cards.
    if nm <= 10:
        base = "MN6105A" if voltage == "24" else "MN6105C"
    elif nm <= 25:
        base = "ML7984A" if voltage == "24" else "ML7983A"
    else:
        base = "ML7421A" if voltage == "24" else "ML7421C"
    if modulating and nm <= 10:
        base = f"{base}1007"
    if aux:
        base = f"{base}S" if not base.endswith("S") else base
    return f"Honeywell {base}"


def _jci_air(nm: int, voltage: str, *, aux: bool) -> str:
    if nm <= 10:
        code = "M9104-AGA-2" if voltage == "24" else "M9104-AGA-3"
    elif nm <= 25:
        code = "M9120-GGA-24" if voltage == "24" else "M9120-GGA-230"
    else:
        code = "M9220-GGA-24" if voltage == "24" else "M9220-GGA-230"
    if aux:
        code = f"{code}-S"
    return f"Johnson Controls {code}"


def _schneider_air(voltage: str, *, modulating: bool) -> str:
    code = f"MD20A-{voltage}"
    if modulating:
        code += "-SR"
    return f"Schneider Electric {code}"


def _danfoss_air(voltage: str) -> str:
    return f"Danfoss AMV{'320' if voltage == '230' else '310'}"


def _lines_major_air(
    *,
    nm: int,
    voltage: str,
    modulating: bool,
    aux: bool,
    fast: bool,
) -> list[str]:
    """Bullet lines for one edition (major brands only)."""
    family = (_BELIMO_FAST if fast else _BELIMO_AIR).get(nm) or ("NMQ" if fast else "NM")
    siemens = _SIEMENS_AIR.get(nm, "GLB")
    lines = [
        f"– {_belimo_air(family, voltage, modulating=modulating, aux=aux)}",
        f"– {_siemens_air(siemens, voltage, modulating=modulating, aux=aux)}",
        f"– {_honeywell_air(nm, voltage, modulating=modulating, aux=aux)}",
        f"– {_jci_air(nm, voltage, aux=aux)}",
    ]
    if modulating:
        lines.append(f"– {_schneider_air(voltage, modulating=True)}")
    elif voltage == "230":
        lines.append(f"– {_danfoss_air(voltage)}")
    if nm >= 8:
        if voltage == "24":
            lines.append("– Gruner 227C-024-10-S1")
        else:
            lines.append("– Gruner 227C-230-10-S1")
    return lines


def build_damqu_analogs(nm: int) -> str:
    """DA..MQU — fast non-spring, A/AS + D/DS × 24/230."""
    blocks: list[str] = [
        (
            f"Список аналогов для привода заслонки Hoocon серии DA{nm}MQU "
            f"(ускоренное срабатывание, без возвратной пружины, {nm} Нм)"
        ),
        "",
        (
            "Только крупные марки (в т.ч. ушедшие / с ограниченными "
            "поставками в РФ): Belimo, Siemens, Honeywell, "
            "Schneider Electric, Johnson Controls, Gruner."
        ),
        "",
    ]
    for voltage in ("24", "230"):
        for modulating, aux, suf in (
            (False, False, "D"),
            (False, True, "DS"),
            (True, False, "A"),
            (True, True, "AS"),
        ):
            code = f"DA{nm}MQU{voltage}-{suf}"
            mode = "пропорциональное (модулирующее) 0…10 В" if modulating else "2-/3-позиционное"
            aux_note = ", 2×SPDT" if aux else ""
            blocks.append(f"{code} ({voltage} В, {mode}{aux_note}):")
            blocks.extend(
                _lines_major_air(
                    nm=nm,
                    voltage=voltage,
                    modulating=modulating,
                    aux=aux,
                    fast=True,
                ),
            )
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


def build_sa7mu_analogs() -> str:
    """SA7MU smoke — on/off DS/DST, Belimo BEE/BLE class."""
    blocks: list[str] = [
        ("Список аналогов для привода заслонки дымоудаления Hoocon серии SA7MU (без возвратной пружины, 7 Нм)"),
        "",
        "Крупные марки: Belimo, Siemens, Honeywell, Gruner, Johnson Controls.",
        "",
    ]
    for voltage in ("24", "230"):
        for thermal, suf in ((False, "DS"), (True, "DST")):
            code = f"SA7MU{voltage}-{suf}"
            note = ", с термодатчиком" if thermal else ""
            blocks.append(f"{code} ({voltage} В, открыто/закрыто{note}):")
            hw = "MS4120F1006" if voltage == "24" else "MS4120F1206"
            if thermal:
                blocks.extend(
                    [
                        f"– Belimo BEE{voltage}ST",
                        f"– Belimo BLE{voltage}-T",
                        "– Siemens GIB161.1E",
                        f"– Honeywell {hw}",
                        f"– Gruner 340TA-{voltage}-10-S2",
                    ],
                )
            else:
                blocks.extend(
                    [
                        f"– Belimo BEE{voltage}",
                        f"– Belimo BLE{voltage}",
                        "– Siemens GIB131.1E",
                        f"– Honeywell {hw}",
                        f"– Johnson Controls M9220-AGA-{voltage}",
                        f"– Gruner 340-{voltage}-10-S2",
                    ],
                )
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


def build_hva_analogs(nm: int, *, fast: bool) -> str:
    """HVA / HVA-Q — modulating air, optional aux S."""
    label = f"HVA-{nm}{'Q' if fast else ''}"
    if fast:
        kind = "ускоренное срабатывание"
    else:
        kind = "стандартное время поворота"
    blocks: list[str] = [
        (
            f"Список аналогов для привода заслонки Hoocon серии {label} "
            f"({kind}, без возвратной пружины, "
            f"пропорциональное управление, {nm} Нм)"
        ),
        "",
        ("Крупные марки: Belimo, Siemens, Honeywell, Schneider Electric, Johnson Controls, Danfoss, Gruner."),
        "",
    ]
    for voltage in ("24", "230"):
        for aux in (False, True):
            s = "S" if aux else ""
            code = f"HVA{voltage}{s}-{nm}{'Q' if fast else ''}"
            aux_note = ", со вспомогательными переключателями" if aux else ""
            blocks.append(f"{code} ({voltage} В{aux_note}):")
            blocks.extend(
                _lines_major_air(
                    nm=nm,
                    voltage=voltage,
                    modulating=True,
                    aux=aux,
                    fast=fast,
                ),
            )
            if not aux and voltage == "230":
                blocks.append(f"– {_danfoss_air(voltage)}")
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


def build_hvd_air_analogs(nm: int, *, fast: bool) -> str:
    """HVD / HVD-Q — on/off air (2-/3-point), optional aux S."""
    label = f"HVD-{nm}{'Q' if fast else ''}"
    if fast:
        kind = "ускоренное срабатывание"
    else:
        kind = "стандартное время поворота"
    blocks: list[str] = [
        (
            f"Список аналогов для привода заслонки Hoocon серии {label} "
            f"({kind}, без возвратной пружины, "
            f"2-/3-позиционное управление, {nm} Нм)"
        ),
        "",
        ("Крупные марки: Belimo, Siemens, Honeywell, Johnson Controls, Danfoss, Gruner."),
        "",
    ]
    for voltage in ("24", "230"):
        for aux in (False, True):
            s = "S" if aux else ""
            code = f"HVD{voltage}{s}-{nm}{'Q' if fast else ''}"
            aux_note = ", со вспомогательными переключателями" if aux else ""
            blocks.append(f"{code} ({voltage} В{aux_note}):")
            blocks.extend(
                _lines_major_air(
                    nm=nm,
                    voltage=voltage,
                    modulating=False,
                    aux=aux,
                    fast=fast,
                ),
            )
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


def build_qx_analogs(brand: str, nm: int) -> str:
    """HVA/HVD-QX — electronic fail-safe (capacitor). Major brands with caveats."""
    brand_u = brand.upper()
    control = "пропорциональное (модулирующее)" if brand_u == "HVA" else "2-/3-позиционное"
    blocks: list[str] = [
        (
            f"Список близких по классу аналогов для {brand_u}-{nm}QX "
            f"(электронный отказоустойчивый привод, {control}, {nm} Нм)"
        ),
        "",
        (
            "Прямых аналогов мало: ориентир — линейки Belimo SuperCap / Fail-Safe "
            "и Siemens / Honeywell с электронным возвратом. Перед заменой "
            "сверяйте время резерва и схему подключения."
        ),
        "",
    ]
    modulating = brand_u == "HVA"
    for voltage in ("24", "230"):
        for aux in (False, True):
            s = "S" if aux else ""
            code = f"{brand_u}{voltage}{s}-{nm}QX"
            blocks.append(f"{code} ({voltage} В):")
            fam = _BELIMO_FAST.get(nm) or "NMQ"
            # Belimo electronic fail-safe: same family class; confirm SuperCap docs.
            bel = _belimo_air(fam, voltage, modulating=modulating, aux=aux)
            blocks.append(f"– {bel} (класс; уточняйте Fail-Safe / SuperCap)")
            siemens = _siemens_air(
                _SIEMENS_AIR.get(nm, "GLB"),
                voltage,
                modulating=modulating,
                aux=aux,
            )
            blocks.append(f"– {siemens} (электронный fail-safe — каталог Siemens)")
            honey = _honeywell_air(
                nm,
                voltage,
                modulating=modulating,
                aux=aux,
            )
            blocks.append(f"– {honey} (серии с электронным возвратом)")
            blocks.append("")
    blocks.append(_FOOTNOTE)
    return normalize_tech_copy("\n".join(blocks).strip())


_DAMQU_SLUG = re.compile(r"(?i)^privod-vozdushniy-da(?P<nm>\d+)mqu-\d+nm$")
_HVA_STD = re.compile(r"(?i)^privod-vozdushniy-hva-(?P<nm>\d+)nm$")
_HVA_Q = re.compile(
    r"(?i)^privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-(?P<nm>\d+)nm$",
)
_HVA_QX = re.compile(r"(?i)^privod-vozdushniy-kondensator-hva-(?P<nm>\d+)qx$")
_HVD_STD = re.compile(r"(?i)^privod-vozdushniy-hvd-(?P<nm>\d+)nm$")
_HVD_Q = re.compile(r"(?i)^privod-vozdushniy-hvd-(?P<nm>\d+)q$")
_HVD_QX = re.compile(r"(?i)^privod-vozdushniy-kondensator-hvd-(?P<nm>\d+)qx$")


def analogs_text_for_product(product: Product) -> str | None:
    """Return curated major-brand analogs for a known gap product slug."""
    slug = product.slug or ""
    if slug == "privod-dimoudaleniya-7nm":
        return build_sa7mu_analogs()
    m = _DAMQU_SLUG.match(slug)
    if m:
        return build_damqu_analogs(int(m.group("nm")))
    m = _HVA_STD.match(slug)
    if m:
        return build_hva_analogs(int(m.group("nm")), fast=False)
    m = _HVA_Q.match(slug)
    if m:
        return build_hva_analogs(int(m.group("nm")), fast=True)
    m = _HVA_QX.match(slug)
    if m:
        return build_qx_analogs("HVA", int(m.group("nm")))
    m = _HVD_STD.match(slug)
    if m:
        return build_hvd_air_analogs(int(m.group("nm")), fast=False)
    m = _HVD_Q.match(slug)
    if m:
        return build_hvd_air_analogs(int(m.group("nm")), fast=True)
    m = _HVD_QX.match(slug)
    if m:
        return build_qx_analogs("HVD", int(m.group("nm")))
    return None


def apply_major_analogs_enrichment(
    *,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Write curated analogs onto empty (or all, if force) matching products/SKUs."""
    summary: dict[str, Any] = {
        "products": 0,
        "skus": 0,
        "skipped_filled": 0,
        "skipped_unknown": 0,
        "dry_run": dry_run,
        "force": force,
        "slugs": [],
    }
    products = Product.objects.all().order_by("slug")
    for product in products:
        text = analogs_text_for_product(product)
        if text is None:
            summary["skipped_unknown"] += 1
            continue
        existing = (product.analogs_text or "").strip()
        if existing and not force:
            summary["skipped_filled"] += 1
            continue
        summary["products"] += 1
        summary["slugs"].append(product.slug)
        if dry_run:
            continue
        product.analogs_text = text
        product.save(update_fields=["analogs_text", "updated_at"])
        for sku in SKU.objects.filter(product=product):
            sku.analogs_text = filter_analogs_for_sku(text, sku.sku_code)
            sku.save(update_fields=["analogs_text", "updated_at"])
            summary["skus"] += 1
    return summary
