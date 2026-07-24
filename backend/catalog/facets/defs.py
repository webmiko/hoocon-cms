"""Facet definitions and Attribute↔facet matching.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

from dataclasses import dataclass

from catalog.models import Attribute, AttributeValue


@dataclass(frozen=True, slots=True)
class FacetDef:
    """One public filter facet."""

    key: str
    label: str
    name_substrings: tuple[str, ...]
    legacy_slugs: tuple[str, ...] = ()
    # Extra: Attribute.name "Мощность" often stores Нм (Tilda mislabel).
    include_power_as_moment: bool = False


# Order = highlight priority on catalog cards / PDP hero.
FACET_DEFS: tuple[FacetDef, ...] = (
    FacetDef(
        key="moment",
        label="Крутящий момент",
        name_substrings=("крутящий момент", "момент"),
        legacy_slugs=("moment",),
        include_power_as_moment=True,
    ),
    FacetDef(
        key="voltage",
        label="Напряжение",
        name_substrings=("напряжение",),
    ),
    FacetDef(
        key="control",
        label="Управление",
        name_substrings=("управление",),
        legacy_slugs=("control",),
    ),
    FacetDef(
        key="area",
        label="Площадь заслонки",
        name_substrings=("площадь",),
        legacy_slugs=("2",),  # historical slug from ETL for area
    ),
    FacetDef(
        key="aux_switch",
        label="Вспомогательный переключатель",
        name_substrings=("вспомогательн",),
    ),
    FacetDef(
        key="temp_sensor",
        label="Термодатчик",
        name_substrings=("термодатчик", "датчик температуры"),
        legacy_slugs=("temp-sensor",),
    ),
    FacetDef(
        key="dn",
        label="DN",
        name_substrings=("dn",),
        legacy_slugs=("dn",),
    ),
    FacetDef(
        key="ways",
        label="Тип крана",
        name_substrings=("вид крана", "тип крана"),
    ),
    FacetDef(
        key="kvs",
        label="Kvs (м³/ч)",
        name_substrings=("kvs",),
        legacy_slugs=("kvs",),
    ),
    FacetDef(
        key="material",
        label="Материал корпуса",
        name_substrings=("материал корпуса",),
        legacy_slugs=("material",),
    ),
    # Belimo codes: card «Аналоги» text, SKU.analog_belimo_code, or ТТХ inference.
    FacetDef(
        key="analog",
        label="Аналоги",
        name_substrings=(),
        legacy_slugs=("analog_belimo_code",),
    ),
)

FACET_BY_KEY: dict[str, FacetDef] = {f.key: f for f in FACET_DEFS}
FACET_KEYS: frozenset[str] = frozenset(FACET_BY_KEY)

# Brass series 8100 (category ``sharovye-krany``): fixed filter set + order.
BALL_VALVE_8100_FACET_KEYS: tuple[str, ...] = (
    "dn",
    "ways",
    "kvs",
    "material",
)

# Category slug → ordered facet keys (strict subset of FACET_DEFS).
CATEGORY_FACET_KEYS: dict[str, tuple[str, ...]] = {
    "sharovye-krany": BALL_VALVE_8100_FACET_KEYS,
}

# Extra PDP/card rows (not catalog filters): after primary facets.
EXTRA_HIGHLIGHT_DEFS: tuple[FacetDef, ...] = (
    FacetDef(
        key="control_signal",
        label="Управляющий сигнал Y",
        name_substrings=("управляющий сигнал", "сигнал управления"),
        legacy_slugs=("control-signal",),
    ),
    FacetDef(
        key="feedback_signal",
        label="Обратная связь U",
        name_substrings=("обратная связь", "сигнал обратной связи"),
        legacy_slugs=("feedback-signal",),
    ),
    FacetDef(
        key="runtime",
        label="Время поворота",
        name_substrings=("время поворота", "время срабатывания"),
    ),
    FacetDef(
        key="dimensions",
        label="Габаритные размеры",
        name_substrings=("габарит",),
    ),
    FacetDef(
        key="weight",
        label="Масса",
        name_substrings=("масса", "вес"),
    ),
    FacetDef(
        key="ip",
        label="Степень защиты корпуса",
        name_substrings=("степень защиты",),
        legacy_slugs=("ip-rating",),
    ),
    FacetDef(
        key="compatible-actuators",
        label="Совместимый привод",
        name_substrings=("совместимый привод",),
        legacy_slugs=("compatible-actuators",),
    ),
    FacetDef(
        key="bracket",
        label="Кронштейн",
        name_substrings=("кронштейн",),
        legacy_slugs=("bracket",),
    ),
)


def attribute_matches_facet(attr: Attribute, facet: FacetDef) -> bool:
    """Return True if Attribute belongs to the facet definition."""
    if facet.key == "analog":
        # Codes live on SKU.analog_belimo_code, not AttributeValue.
        return False
    slug = attr.slug or ""
    if slug in facet.legacy_slugs:
        return True
    # Tilda used ``kvs-3`` etc. for ball-valve flow coefficients.
    if facet.key == "kvs" and slug.casefold().startswith("kvs"):
        return True
    name = (attr.name or "").casefold()
    if facet.include_power_as_moment and "мощность" in name:
        return True
    # «Управление» facet must not pick manual override / Y-signal rows.
    if facet.key == "control":
        if slug in {"manual-override", "control-signal", "feedback-signal"}:
            return False
        if "ручн" in name or "сигнал" in name or "обратная связь" in name:
            return False
        return name == "управление" or name.startswith("управление ")
    if facet.key == "control_signal":
        if slug == "feedback-signal" or "обратная связь" in name:
            return False
    if facet.key == "feedback_signal":
        if slug == "control-signal" or ("управляющ" in name and "обратн" not in name):
            return False
    # Nominal voltage only — not «Диапазон напряжения».
    if facet.key == "voltage":
        if slug == "voltage-range" or "диапазон" in name:
            return False
    # Body material only — not «Золотниковый шток и шар» (ball-stem-material).
    if facet.key == "material":
        if slug == "ball-stem-material" or "золотников" in name:
            return False
    if not facet.name_substrings:
        return False
    return any(token in name for token in facet.name_substrings)


def attribute_ids_for_facet(facet: FacetDef) -> list[int]:
    """Resolve Attribute PKs that feed a facet (cached per request via caller)."""
    ids: list[int] = []
    for attr in Attribute.objects.all().only("id", "name", "slug"):
        if attribute_matches_facet(attr, facet):
            # For mislabeled «Мощность»: only if some values look like torque.
            if facet.include_power_as_moment and "мощность" in (attr.name or "").casefold():
                if not AttributeValue.objects.filter(
                    attribute=attr,
                    value__icontains="Нм",
                ).exists():
                    continue
            ids.append(attr.id)
    return ids
