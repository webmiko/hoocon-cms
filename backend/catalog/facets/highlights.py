"""Card/PDP ТТХ highlights and modulating-signal attrs.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from catalog.facets.aux import format_aux_switch_display
from catalog.facets.dedupe import dedupe_attribute_values
from catalog.facets.defs import (
    EXTRA_HIGHLIGHT_DEFS,
    FACET_BY_KEY,
    FACET_DEFS,
    attribute_matches_facet,
)
from catalog.facets.normalize import normalize_area_attribute_value
from catalog.models import SKU, Attribute, AttributeValue


def highlights_for_sku(
    attribute_values: Iterable[AttributeValue],
    *,
    limit: int = 9,
    description: str = "",
    sku_code: str | None = None,
    category_slug: str | None = None,
) -> list[dict[str, str]]:
    """Pick compact ТТХ rows for catalog cards / PDP hero.

    Args:
        attribute_values: Prefetched AttributeValue rows (with attribute).
        limit: Max rows to return.
        description: SKU description (used to resolve SPDT count).
        sku_code: Edition code for voltage / control / aux canon.
        category_slug: Category slug for control ON/OFF vs floating.

    Returns:
        ``[{key, name, value, unit}]`` in facet priority order (deduped by key).
    """
    values = dedupe_attribute_values(attribute_values)
    by_key: dict[str, dict[str, str]] = {}
    highlight_defs = (*FACET_DEFS, *EXTRA_HIGHLIGHT_DEFS)
    for av in values:
        attr = cast(Attribute, av.attribute)
        for facet in highlight_defs:
            if facet.key in by_key:
                continue
            if not attribute_matches_facet(attr, facet):
                continue
            # Skip mislabeled power unless value looks like torque.
            if (
                facet.include_power_as_moment
                and "мощность" in (attr.name or "").casefold()
                and "нм" not in str(av.value).casefold()
            ):
                continue

            display = str(av.value).strip()
            label = facet.label
            if facet.key == "control":
                from catalog.etl.tech_copy import normalize_control_attribute_value

                display = normalize_control_attribute_value(
                    display,
                    sku_code=sku_code,
                    category_slug=category_slug,
                )
            if facet.key == "area":
                display = normalize_area_attribute_value(display)
            if facet.key == "voltage":
                from catalog.etl.tech_copy import normalize_voltage_attribute_value

                display = normalize_voltage_attribute_value(
                    display,
                    sku_code=sku_code,
                )
            if facet.key == "aux_switch":
                formatted = format_aux_switch_display(
                    display,
                    description=description,
                    sku_code=sku_code,
                )
                if formatted is None:
                    continue
                display = formatted
                label = "Вспом. переключатель"

            if facet.key in {"control_signal", "feedback_signal"}:
                from catalog.etl.tech_copy import (
                    CONTROL_SIGNAL_Y_LABEL,
                    FEEDBACK_SIGNAL_U_LABEL,
                    normalize_modulating_signal_value,
                )

                display = normalize_modulating_signal_value(display)
                label = CONTROL_SIGNAL_Y_LABEL if facet.key == "control_signal" else FEEDBACK_SIGNAL_U_LABEL
            if facet.key == "runtime":
                from catalog.etl.tech_copy import (
                    attribute_display_unit,
                    normalize_running_time_value,
                )

                display = normalize_running_time_value(display)
                unit = attribute_display_unit(display, attr.unit or "")
            elif facet.key == "kvs":
                # Kvs label already includes (м³/ч) — avoid «Kvs (м³/ч): 1,6 м³/ч».
                unit = ""
            else:
                from catalog.etl.tech_copy import attribute_display_unit

                unit = attribute_display_unit(display, attr.unit or "")

            by_key[facet.key] = {
                "key": facet.key,
                "name": label,
                "value": display,
                "unit": unit,
            }
            break
        if len(by_key) >= limit + 2:
            # Allow room for Y/U inject before final trim.
            break

    _ensure_modulating_signal_highlights(by_key)

    ordered: list[dict[str, str]] = []
    seen: set[str] = set()
    for facet in highlight_defs:
        # Inserted immediately after «Управление», not at EXTRA position.
        if facet.key in {"control_signal", "feedback_signal"}:
            continue
        if facet.key in by_key and facet.key not in seen:
            ordered.append(by_key[facet.key])
            seen.add(facet.key)
        if facet.key == "control":
            for signal_key in ("control_signal", "feedback_signal"):
                if signal_key in by_key and signal_key not in seen:
                    ordered.append(by_key[signal_key])
                    seen.add(signal_key)
        if len(ordered) >= limit:
            break
    return ordered


def _ensure_modulating_signal_highlights(
    by_key: dict[str, dict[str, str]],
) -> None:
    """Require Y/U signal rows when control is пропорциональное."""
    from catalog.etl.tech_copy import (
        CONTROL_SIGNAL_Y_CANON,
        CONTROL_SIGNAL_Y_LABEL,
        FEEDBACK_SIGNAL_U_CANON,
        FEEDBACK_SIGNAL_U_LABEL,
        is_proportional_control,
    )

    control = by_key.get("control", {}).get("value", "")
    if not is_proportional_control(control):
        by_key.pop("control_signal", None)
        by_key.pop("feedback_signal", None)
        return
    if "control_signal" not in by_key:
        by_key["control_signal"] = {
            "key": "control_signal",
            "name": CONTROL_SIGNAL_Y_LABEL,
            "value": CONTROL_SIGNAL_Y_CANON,
            "unit": "",
        }
    if "feedback_signal" not in by_key:
        by_key["feedback_signal"] = {
            "key": "feedback_signal",
            "name": FEEDBACK_SIGNAL_U_LABEL,
            "value": FEEDBACK_SIGNAL_U_CANON,
            "unit": "",
        }


def ensure_modulating_signal_attributes(sku: SKU) -> int:
    """Persist Belimo Y/U signal EAV for пропорциональное editions.

    Args:
        sku: Published or draft SKU with control attribute.

    Returns:
        Number of AttributeValue rows created or updated.
    """
    from catalog.etl.tech_copy import (
        CONTROL_SIGNAL_Y_CANON,
        CONTROL_SIGNAL_Y_LABEL,
        CONTROL_SIGNAL_Y_SLUG,
        FEEDBACK_SIGNAL_U_CANON,
        FEEDBACK_SIGNAL_U_LABEL,
        FEEDBACK_SIGNAL_U_SLUG,
        is_proportional_control,
        normalize_control_attribute_value,
    )
    from catalog.sku_access import sku_category_slug_or_empty

    control_raw = ""
    for av in sku.attribute_values.select_related("attribute"):
        attr = cast(Attribute, av.attribute)
        if attribute_matches_facet(attr, FACET_BY_KEY["control"]):
            control_raw = str(av.value or "")
            break
    control = normalize_control_attribute_value(
        control_raw,
        sku_code=sku.sku_code,
        category_slug=sku_category_slug_or_empty(sku) or None,
    )
    if not is_proportional_control(control):
        return 0

    changed = 0
    specs = (
        (CONTROL_SIGNAL_Y_SLUG, CONTROL_SIGNAL_Y_LABEL, CONTROL_SIGNAL_Y_CANON),
        (FEEDBACK_SIGNAL_U_SLUG, FEEDBACK_SIGNAL_U_LABEL, FEEDBACK_SIGNAL_U_CANON),
    )
    for slug, name, value in specs:
        attr, _created = Attribute.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "unit": ""},
        )
        if attr.name != name:
            attr.name = name
            attr.save(update_fields=["name"])
        av, created = AttributeValue.objects.get_or_create(
            sku=sku,
            attribute=attr,
            defaults={"value": value},
        )
        if created:
            changed += 1
            continue
        if (av.value or "").strip() != value:
            av.value = value
            av.save(update_fields=["value"])
            changed += 1
    return changed
