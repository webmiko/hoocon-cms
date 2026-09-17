"""Cross-category quiz analogs when the primary selection is out of stock.

Kit branch: factory ``komplekty`` unavailable → brass/flanged valve + compatible
drive from EAV «Совместимый привод» + bracket (BR-M / BR-ML / BR-H).
"""

from __future__ import annotations

import re
from typing import Any, Literal, cast

from django.db.models import Prefetch, QuerySet
from rest_framework.request import Request

from catalog.ball_valve_kit import (
    build_ball_valve_kit_options,
    is_ball_valve_sku,
    parse_drive_families,
    resolve_bracket_for_drive,
)
from catalog.facets import FACET_BY_KEY, filter_skus_by_facet
from catalog.models import SKU, ProductImage
from catalog.ordering import annotate_moment_nm, catalog_list_order_by
from catalog.series_categories import spec_order_case

QuizVoltage = Literal["24", "230", "skip"]
QuizControl = Literal["onoff", "modulating", "skip"]
QuizAuxSwitch = Literal["yes", "no", "skip"]

_BALL_VALVE_CATEGORY = "sharovye-krany"
_FACET_KEYS_FOR_VALVES = frozenset({"dn", "kvs", "ways"})


def quiz_drive_suffix(
    control: QuizControl | str | None,
    aux_switch: QuizAuxSwitch | str | None,
) -> str:
    """Map quiz control/aux answers to a DA edition suffix.

    Args:
        control: ``onoff`` | ``modulating`` | ``skip``.
        aux_switch: ``yes`` | ``no`` | ``skip``.

    Returns:
        One of ``-D``, ``-DS``, ``-A``, ``-AS`` (default ``-D``).
    """
    modulating = control == "modulating"
    aux = aux_switch == "yes"
    if modulating:
        return "-AS" if aux else "-A"
    return "-DS" if aux else "-D"


def _normalize_code(code: str) -> str:
    return (code or "").casefold().replace(" ", "").replace("-", "")


def family_matches_voltage(family: str, voltage: QuizVoltage | str | None) -> bool:
    """True when a drive family article encodes the requested voltage."""
    if not voltage or voltage == "skip":
        return True
    fam = (family or "").upper()
    if voltage == "230":
        return "230" in fam
    return fam.endswith("24") or bool(re.search(r"(?:FU|MU|SA|HVD|HVA)24", fam))


def format_drive_sku_code(family: str, suffix: str) -> str:
    """Canonical Hoocon drive article: ``DA6MU24`` + ``-D`` → ``DA6MU24-D``."""
    return f"{family}{suffix}"


def pick_drive_family(
    families: list[str],
    voltage: QuizVoltage | str | None,
    *,
    prefer_in_stock: bool = True,
    drive_by_family: dict[str, SKU] | None = None,
) -> str | None:
    """Choose the first compatible drive family for quiz voltage/stock."""
    matched = [family for family in families if family_matches_voltage(family, voltage)]
    if not matched:
        return None
    if prefer_in_stock and drive_by_family:
        for family in matched:
            drive = drive_by_family.get(family)
            if drive is not None and drive.in_stock:
                return family
    return matched[0]


def resolve_published_drive(
    family: str,
    suffix: str,
    *,
    queryset: QuerySet[SKU] | None = None,
) -> SKU | None:
    """Find a published drive SKU for ``family`` + edition ``suffix``."""
    target = _normalize_code(format_drive_sku_code(family, suffix))
    qs = queryset if queryset is not None else _published_sku_qs()
    for sku in qs.filter(sku_code__istartswith="DA"):
        if _normalize_code(sku.sku_code or "") == target:
            return sku
    return None


def resolve_published_bracket(code: str) -> SKU | None:
    """Resolve BR-M / BR-ML / BR-H adapter SKU by exact article."""
    needle = (code or "").strip().upper()
    if not needle:
        return None
    return _published_sku_qs().filter(sku_code__iexact=needle).first()


def _published_sku_qs() -> QuerySet[SKU]:
    return (
        SKU.objects.filter(is_published=True)
        .select_related("product", "product__category")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_published=True).order_by(
                    "sort_order",
                    "id",
                ),
            ),
        )
        .order_by("sku_code")
    )


def _query_params(request: Request | Any) -> Any:
    """DRF ``query_params`` with Django ``GET`` fallback for unit tests."""
    return getattr(request, "query_params", request.GET)


def _valve_queryset(request: Request, limit: int) -> list[SKU]:
    """Published ball valves filtered by quiz DN/Kvs/ways facet params."""
    qs = annotate_moment_nm(
        _published_sku_qs()
        .filter(product__category__slug=_BALL_VALVE_CATEGORY)
        .annotate(
            category_spec_order=spec_order_case(
                slug_field="product__category__slug",
            ),
        ),
    ).order_by(*catalog_list_order_by())

    params = _query_params(request)
    for key in _FACET_KEYS_FOR_VALVES:
        value = params.get(key)
        if not value:
            continue
        facet = FACET_BY_KEY.get(key)
        if facet is None:
            continue
        qs = filter_skus_by_facet(qs, facet, value)

    rows = list(qs[: limit * 4])
    rows.sort(key=lambda row: (0 if row.in_stock else 1, row.sku_code or ""))
    return rows[:limit]


def build_kit_bundle_for_valve(
    valve_sku: SKU,
    voltage: QuizVoltage | str | None,
    control: QuizControl | str | None,
    aux_switch: QuizAuxSwitch | str | None,
    *,
    drive_lookup: QuerySet[SKU] | None = None,
) -> dict[str, Any] | None:
    """Assemble valve + drive + bracket when a factory kit is unavailable.

    Args:
        valve_sku: Published bare ball-valve SKU (not H81/H8205 kit).
        voltage: Quiz voltage answer.
        control: Quiz control answer.
        aux_switch: Quiz aux-switch answer.
        drive_lookup: Optional queryset limiting drive resolution.

    Returns:
        Dict with ``valve``, ``drive``, ``bracket``, ``drive_code``,
        ``in_stock`` — or ``None`` when pairing is impossible.
    """
    if not is_ball_valve_sku(valve_sku):
        return None
    kit_options = build_ball_valve_kit_options(valve_sku)
    if kit_options is None:
        families = parse_drive_families(_compatible_actuators_text(valve_sku))
        if not families:
            return None
        kit_options = {
            "drive_families": families,
            "suffixes": ["-D", "-DS", "-A", "-AS"],
            "bracket_by_drive": {
                family: resolve_bracket_for_drive(
                    family,
                    flanged=_is_flanged_valve(valve_sku),
                )
                for family in families
            },
        }

    suffix = quiz_drive_suffix(control, aux_switch)
    families = list(kit_options["drive_families"])
    drive_by_family = {family: resolve_published_drive(family, suffix, queryset=drive_lookup) for family in families}
    family = pick_drive_family(
        families,
        voltage,
        prefer_in_stock=True,
        drive_by_family={k: v for k, v in drive_by_family.items() if v is not None},
    )
    if family is None:
        return None
    drive = drive_by_family.get(family) or resolve_published_drive(
        family,
        suffix,
        queryset=drive_lookup,
    )
    if drive is None:
        return None

    bracket_code = kit_options["bracket_by_drive"].get(family) or resolve_bracket_for_drive(
        family,
        flanged=_is_flanged_valve(valve_sku),
    )
    bracket = resolve_published_bracket(bracket_code)
    components_in_stock = valve_sku.in_stock and drive.in_stock and (bracket is None or bracket.in_stock)
    return {
        "valve": valve_sku,
        "drive": drive,
        "bracket": bracket,
        "drive_code": format_drive_sku_code(family, suffix),
        "bracket_code": bracket_code,
        "in_stock": components_in_stock,
    }


def find_kit_analog_bundles(
    request: Request,
    *,
    voltage: QuizVoltage | str | None = None,
    control: QuizControl | str | None = None,
    aux_switch: QuizAuxSwitch | str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Build kit analog bundles from matching bare ball valves.

    Args:
        request: DRF request with optional ``dn`` / ``kvs`` / ``ways`` facets.
        voltage: Raw quiz voltage (``24`` / ``230`` / ``skip``).
        control: Raw quiz control (``onoff`` / ``modulating`` / ``skip``).
        aux_switch: Raw quiz aux (``yes`` / ``no`` / ``skip``).
        limit: Max bundles to return.

    Returns:
        Bundle dicts ready for serialization (model instances under keys).
    """
    params = _query_params(request)
    voltage = voltage or params.get("quiz_voltage")
    control = control or params.get("quiz_control")
    aux_switch = aux_switch or params.get("quiz_aux")

    valves = _valve_queryset(request, limit)
    if not valves:
        return []

    drive_lookup = _published_sku_qs().filter(sku_code__istartswith="DA")
    bundles: list[dict[str, Any]] = []
    for valve in valves:
        bundle = build_kit_bundle_for_valve(
            valve,
            voltage,
            control,
            aux_switch,
            drive_lookup=drive_lookup,
        )
        if bundle is None:
            continue
        bundles.append(bundle)

    bundles.sort(
        key=lambda row: (
            0 if row["in_stock"] else 1,
            row["valve"].sku_code or "",
        ),
    )
    return bundles[:limit]


def _compatible_actuators_text(sku: SKU) -> str:
    from catalog.models import Attribute

    for av in sku.attribute_values.all():
        attr = cast(Attribute, av.attribute)
        slug = (attr.slug or "").casefold()
        name = (attr.name or "").casefold()
        if slug == "compatible-actuators" or ("совместим" in name and "привод" in name):
            return str(av.value or "").strip()
    return ""


def _is_flanged_valve(sku: SKU) -> bool:
    from catalog.models import Attribute

    for av in sku.attribute_values.all():
        attr = cast(Attribute, av.attribute)
        slug = (attr.slug or "").casefold()
        val = str(av.value or "").casefold()
        if slug == "material" and "вчшг" in val:
            return True
        if slug in {"connection", "thread"} and "фланц" in val:
            return True
    return False
