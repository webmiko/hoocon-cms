"""Curated «Аналоги» copy for gap / empty cards — guidance, not pairs.

Policy: a bullet «– Brand ARTICLE» reads as a confirmed replacement pair, and
none of the generated pairs is datasheet-confirmed — matching torque/area is
not proof. Builders below therefore emit the series title, the class
guidance (incl. the major-brands line: Belimo, Siemens, Honeywell, Schneider
Electric, Johnson Controls, Danfoss, Gruner) and the selection footnote only.
Do **not** invent obscure OEM clones (Nanotek, Dastech, Lufberg, BVM, …).
Fill only when ``Product.analogs_text`` is empty (unless ``force=True``).
"""

from __future__ import annotations

import re
from typing import Any

from catalog.etl.attr_write import write_copy
from catalog.etl.html_text import filter_analogs_for_sku
from catalog.etl.tech_copy import normalize_tech_copy
from catalog.models import SKU, Product

_FOOTNOTE = normalize_tech_copy(
    "При выборе аналога сверяйте крутящий момент, напряжение, "
    "тип управления, наличие вспомогательных переключателей "
    "и габариты монтажа. Точные артикулы ушедших из РФ брендов "
    "уточняйте по паспорту / шильдику заменяемого привода.",
)

# A bullet «– Brand ARTICLE» in this copy would read as a confirmed pair.
# None is datasheet-confirmed, so the builders below print no bullets —
# only the class guidance and the selection footnote.


def build_damqu_analogs(nm: int) -> str:
    """DA..MQU — fast non-spring. Guidance only: no unverified pair articles."""
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
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())


def build_sa7mu_analogs() -> str:
    """SA7MU smoke — no Belimo (smallest smoke class is 15 Нм); guidance only."""
    blocks: list[str] = [
        ("Список аналогов для привода заслонки дымоудаления Hoocon серии SA7MU (без возвратной пружины, 7 Нм)"),
        "",
        "Крупные марки: Siemens, Honeywell, Gruner, Johnson Controls.",
        "",
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())


def build_hva_analogs(nm: int, *, fast: bool) -> str:
    """HVA / HVA-Q — modulating air. Guidance only: no unverified pair articles."""
    label = f"HVA-{nm}{'Q' if fast else ''}"
    kind = "ускоренное срабатывание" if fast else "стандартное время поворота"
    blocks: list[str] = [
        (
            f"Список аналогов для привода заслонки Hoocon серии {label} "
            f"({kind}, без возвратной пружины, "
            f"пропорциональное управление, {nm} Нм)"
        ),
        "",
        ("Крупные марки: Belimo, Siemens, Honeywell, Schneider Electric, Johnson Controls, Danfoss, Gruner."),
        "",
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())


def build_hvd_air_analogs(nm: int, *, fast: bool) -> str:
    """HVD / HVD-Q — on/off air (2-/3-point). Guidance only, no pair articles."""
    label = f"HVD-{nm}{'Q' if fast else ''}"
    kind = "ускоренное срабатывание" if fast else "стандартное время поворота"
    blocks: list[str] = [
        (
            f"Список аналогов для привода заслонки Hoocon серии {label} "
            f"({kind}, без возвратной пружины, "
            f"2-/3-позиционное управление, {nm} Нм)"
        ),
        "",
        ("Крупные марки: Belimo, Siemens, Honeywell, Johnson Controls, Danfoss, Gruner."),
        "",
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())


def build_qx_analogs(brand: str, nm: int) -> str:
    """HVA/HVD-QX — capacitor fail-safe, not fast Q and not a spring.

    LMQ…GMQ are fast and non-fail-safe. GCA returns by spring. MN6105 has
    no emergency return. The only direct electronic-fail-safe article in
    this torque band is Belimo SuperCap when its area is not above ours
    (NKQ 1.2 m², 24 V; fail-safe brochure 2026) — printed once that pair is
    datasheet-confirmed, not here.
    """
    brand_u = brand.upper()
    control = "пропорциональное (модулирующее)" if brand_u == "HVA" else "2-/3-позиционное"
    blocks: list[str] = [
        (
            f"Список аналогов для {brand_u}-{nm}QX "
            f"(электронный отказоустойчивый привод, конденсаторный возврат, "
            f"{control}, {nm} Нм)"
        ),
        "",
        (
            "Подходят только приводы с электронным аварийным возвратом "
            "(конденсаторный / SuperCap-класс). Пружинный возврат и приводы "
            "без аварийного возврата не подходят."
        ),
        "",
        _FOOTNOTE,
    ]
    return normalize_tech_copy("\n".join(blocks).strip())


_DAMU_SLUG = re.compile(r"(?i)^privod-vozdushniy-bez-pruzhini-damu-(?P<nm>\d+)nm$")
_DAMQU_SLUG = re.compile(r"(?i)^privod-vozdushniy-da(?P<nm>\d+)mqu-\d+nm$")
_SAMU_SLUG = re.compile(r"(?i)^privod-dimoudaleniya-(?P<nm>\d+)nm$")
_DAFU_SLUG = re.compile(r"(?i)^privod-vozdushniy-pruzhina-dafu-(?P<nm>\d+)nm$")
_SAFU_SLUG = re.compile(r"(?i)^privod-protivopozharniy-(?P<nm>\d+)nm$")
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
    from catalog.etl.series_copy_damu_analogs import build_damu_analogs
    from catalog.etl.series_copy_spring_analogs import (
        build_dafu_analogs,
        build_safu_analogs,
        build_samu_analogs,
    )

    slug = product.slug or ""
    if slug == "privod-dimoudaleniya-7nm":
        return build_sa7mu_analogs()
    m = _DAMU_SLUG.match(slug)
    if m:
        return build_damu_analogs(int(m.group("nm")))
    m = _SAMU_SLUG.match(slug)
    if m:
        nm = int(m.group("nm"))
        if nm != 7:
            return build_samu_analogs(nm)
    m = _DAFU_SLUG.match(slug)
    if m:
        return build_dafu_analogs(int(m.group("nm")))
    m = _SAFU_SLUG.match(slug)
    if m:
        return build_safu_analogs(int(m.group("nm")))
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
        write_copy(product, analogs_text=text)
        for sku in SKU.objects.filter(product=product):
            write_copy(sku, analogs_text=filter_analogs_for_sku(text, sku.sku_code))
            summary["skus"] += 1
    return summary
