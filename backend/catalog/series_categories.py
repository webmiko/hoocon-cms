"""Canonical catalog categories from the HOOCON model-series specification.

Source: https://hoocon.ru/statyi/tpost/4uicugaoh1-spetsifikatsiya-modelnogo-ryada-privodov

Actuator families only (six rows of the series table). Ball-valve bodies and
factory valve+actuator kits are separate catalog buckets outside that table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db.models import Case, IntegerField, Value, When

# Article order (ventilation actuators).
_ACTUATOR_SPECS: tuple[tuple[str, str], ...] = (
    (
        "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
        "Электроприводы воздушные без пружинного возврата",
    ),
    (
        "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
        "Электроприводы ускоренные без пружинного возврата",
    ),
    (
        "elektronnye-otkazoustoychivye-vozdushnye-privody",
        "Электронные отказоустойчивые воздушные приводы",
    ),
    (
        "elektroprivody-s-pruzhinnym-vozvratom",
        "Электроприводы с пружинным возвратом",
    ),
    (
        "elektroprivody-protivopozharnye-i-dymovye",
        "Электроприводы противопожарные и дымовые",
    ),
    (
        "elektroprivody-dlya-klapanov-dymoudaleniya",
        "Электроприводы для клапанов дымоудаления",
    ),
)

_BALL_VALVES: tuple[str, str] = ("sharovye-krany", "Шаровые краны")
_KITS: tuple[str, str] = ("komplekty", "Комплекты")

# H8101…H8122 factory kits + H8205 LAV (valve+actuator cards).
_H81_KIT_BLOB = re.compile(
    r"(?i)(?:^|[^a-z0-9])h81(?:01|02|03|04|05|06|07|08|21|22)(?:[^a-z0-9]|$)",
)
_H8205_BLOB = re.compile(r"(?i)(?:^|[^a-z0-9])h8205(?:[^a-z0-9]|$)")

# Slugs that may still exist from Tilda ETL / earlier scrapes → canonical.
_SLUG_ALIASES: dict[str, str] = {
    "elektroprivod-vozdushnoy-zaslonki": ("elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"),
    "elektroprivod-vozdushniy-bez-vozvratnoy-pruzhiny": ("elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"),
    "elektroprivod-vozdushniy-uskorennogo-srabatyvaniya": ("elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata"),
    "elektroprivod-vozdushniy-s-vozvratnoy-pruzhinoy": ("elektroprivody-s-pruzhinnym-vozvratom"),
    "elektroprivod-protivopozharnogo-klapana": ("elektroprivody-protivopozharnye-i-dymovye"),
    "spetsialnaya-protivopozharnaya-seriya": ("elektroprivody-protivopozharnye-i-dymovye"),
    "elektroprivod-klapana-dymoudaleniya": ("elektroprivody-dlya-klapanov-dymoudaleniya"),
    "sharoviy-kran-2-hodovoy": "sharovye-krany",
    "sharoviy-kran-3-hodovoy": "sharovye-krany",
}


@dataclass(frozen=True, slots=True)
class SpecCategory:
    """One catalog category allowed by the series specification."""

    slug: str
    name: str
    sort_order: int


def spec_categories(*, include_ball_valves: bool = True) -> list[SpecCategory]:
    """Return the allowed category list in display order.

    Args:
        include_ball_valves: Append BV bodies + kits buckets (not in the
            actuator table).

    Returns:
        Spec categories with stable sort_order.
    """
    rows = [SpecCategory(slug=slug, name=name, sort_order=i) for i, (slug, name) in enumerate(_ACTUATOR_SPECS)]
    if include_ball_valves:
        for slug, name in (_BALL_VALVES, _KITS):
            rows.append(SpecCategory(slug=slug, name=name, sort_order=len(rows)))
    return rows


def kits_category_slug() -> str:
    """Canonical slug for factory valve+actuator kits."""
    return _KITS[0]


def ball_valves_category_slug() -> str:
    """Canonical slug for bare ball-valve bodies (``8100-bv*``)."""
    return _BALL_VALVES[0]


def allowed_slugs(*, include_ball_valves: bool = True) -> frozenset[str]:
    """Return the set of canonical category slugs."""
    return frozenset(c.slug for c in spec_categories(include_ball_valves=include_ball_valves))


def spec_order_case(*, slug_field: str = "slug") -> Case:
    """Django ``Case`` for series-table category order (filter + catalog cards).

    Maps both canonical slugs and legacy Tilda aliases to the same
    ``sort_order`` so sidebar / list order stays correct before or after
    ``align_categories_to_spec``.

    Args:
        slug_field: Category slug ORM path (``slug`` or ``product__category__slug``).

    Returns:
        Annotation expression; unknown slugs sort last (999).
    """
    order_by_slug: dict[str, int] = {spec.slug: spec.sort_order for spec in spec_categories()}
    for legacy, canonical in _SLUG_ALIASES.items():
        if canonical in order_by_slug:
            order_by_slug[legacy] = order_by_slug[canonical]
    whens = [When(**{slug_field: slug}, then=Value(order)) for slug, order in order_by_slug.items()]
    return Case(*whens, default=Value(999), output_field=IntegerField())


def resolve_alias(slug: str) -> str | None:
    """Map a legacy Tilda slug to a canonical spec slug, if known."""
    if slug in allowed_slugs():
        return slug
    return _SLUG_ALIASES.get(slug)


def legacy_slug_aliases() -> dict[str, str]:
    """Return a copy of Tilda → specification category slug map."""
    return dict(_SLUG_ALIASES)


def classify_series_category(product_slug: str, sku_codes: list[str] | None = None) -> str:
    """Pick the specification category for a product line.

    Args:
        product_slug: Product URL slug (e.g. ``privod-vozdushniy-pruzhina-dafu-3nm``).
        sku_codes: Optional edition codes for disambiguation.

    Returns:
        Canonical category slug from the series table (or ball valves / kits).
    """
    codes = " ".join(sku_codes or []).lower()
    slug = (product_slug or "").lower()
    blob = f"{slug} {codes}"

    # Kits before bare BV: product slugs contain both «sharovoy-kran» and H81xx.
    if (
        _H81_KIT_BLOB.search(blob)
        or _H8205_BLOB.search(blob)
        or "sharovoy-kran-h81" in slug
        or bool(re.fullmatch(r"h81(?:01|02|03|04|05|06|07|08|21|22)", slug))
        or "sharovoy-kran-h82" in slug
    ):
        return _KITS[0]
    if "sharov" in blob or re.search(r"\bbv\d", blob) or "8100-bv" in blob:
        return _BALL_VALVES[0]
    if "dimoudal" in blob or re.search(r"\bsa\d*mu", blob):
        return "elektroprivody-dlya-klapanov-dymoudaleniya"
    if "protivopozhar" in blob or "protivipozhar" in blob or re.search(r"\bsa\d*fu", blob):
        return "elektroprivody-protivopozharnye-i-dymovye"
    if re.search(r"\bda\d*mqu", blob) or "uskorenn" in blob:
        return "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata"
    if re.search(r"\bda\d*eu", blob) or "otkazoustoych" in blob:
        return "elektronnye-otkazoustoychivye-vozdushnye-privody"
    # DAMU / «без пружины» before the generic «пружин» token (bez-pruzhini).
    if re.search(r"\bda\d*mu(?!q)", blob) or re.search(r"bez[-_]?pruzhin", blob):
        return "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"
    if "pruzhin" in blob or re.search(r"\bda\d*fu", blob):
        return "elektroprivody-s-pruzhinnym-vozvratom"
    return "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"
