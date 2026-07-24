"""ТТХ attribute groups for PDP characteristic cards.

Group keys are attached to AttributeValue API rows via slug mapping
(Attribute model has no group column yet).
"""

from __future__ import annotations

from typing import Any

ATTR_GROUP_ELECTRICAL = "electrical"
ATTR_GROUP_FUNCTIONAL = "functional"
ATTR_GROUP_OPERATING = "operating"
ATTR_GROUP_SIZE = "size"
ATTR_GROUP_VALVE = "valve"
ATTR_GROUP_HYDRAULIC = "hydraulic"
ATTR_GROUP_MATERIALS = "materials"

ATTR_GROUP_LABELS: dict[str, str] = {
    ATTR_GROUP_ELECTRICAL: "Электрические параметры",
    ATTR_GROUP_FUNCTIONAL: "Функциональные параметры",
    ATTR_GROUP_OPERATING: "Условия эксплуатации",
    ATTR_GROUP_SIZE: "Размеры и масса",
    ATTR_GROUP_VALVE: "Параметры крана",
    ATTR_GROUP_HYDRAULIC: "Гидравлика",
    ATTR_GROUP_MATERIALS: "Материалы",
}

ATTR_GROUP_ORDER: tuple[str, ...] = (
    ATTR_GROUP_ELECTRICAL,
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
    ATTR_GROUP_VALVE,
    ATTR_GROUP_HYDRAULIC,
    ATTR_GROUP_MATERIALS,
)

# Default slug → group for catalog (actuators + valves).
DEFAULT_ATTR_GROUP_BY_SLUG: dict[str, str] = {
    "voltage": ATTR_GROUP_ELECTRICAL,
    "voltage-range": ATTR_GROUP_ELECTRICAL,
    "power-consumption": ATTR_GROUP_ELECTRICAL,
    "transformer-va": ATTR_GROUP_ELECTRICAL,
    "wire-cross-section": ATTR_GROUP_ELECTRICAL,
    "control-signal": ATTR_GROUP_ELECTRICAL,
    "feedback-signal": ATTR_GROUP_ELECTRICAL,
    "moment": ATTR_GROUP_FUNCTIONAL,
    "damper-area": ATTR_GROUP_FUNCTIONAL,
    "terminal-size": ATTR_GROUP_FUNCTIONAL,
    "rotation-direction": ATTR_GROUP_FUNCTIONAL,
    "manual-override": ATTR_GROUP_FUNCTIONAL,
    "rotation-angle": ATTR_GROUP_FUNCTIONAL,
    "noise": ATTR_GROUP_FUNCTIONAL,
    "position-indication": ATTR_GROUP_FUNCTIONAL,
    "control": ATTR_GROUP_FUNCTIONAL,
    "aux-switch": ATTR_GROUP_FUNCTIONAL,
    "fault-alarm": ATTR_GROUP_FUNCTIONAL,
    "running-time": ATTR_GROUP_FUNCTIONAL,
    "temp-sensor": ATTR_GROUP_FUNCTIONAL,
    "protection-class": ATTR_GROUP_OPERATING,
    "ip-rating": ATTR_GROUP_OPERATING,
    "ambient-temp": ATTR_GROUP_OPERATING,
    "storage-temp": ATTR_GROUP_OPERATING,
    "humidity": ATTR_GROUP_OPERATING,
    "dimensions": ATTR_GROUP_SIZE,
    "shaft-length": ATTR_GROUP_SIZE,
    "shaft-diameter": ATTR_GROUP_SIZE,
    "weight": ATTR_GROUP_SIZE,
    "dn": ATTR_GROUP_VALVE,
    "ways": ATTR_GROUP_VALVE,
    "thread": ATTR_GROUP_VALVE,
    "kvs": ATTR_GROUP_HYDRAULIC,
    "diff-pressure": ATTR_GROUP_HYDRAULIC,
    "compatible-actuators": ATTR_GROUP_VALVE,
    "bracket": ATTR_GROUP_VALVE,
    "medium": ATTR_GROUP_OPERATING,
    "media-temp": ATTR_GROUP_OPERATING,
    "material": ATTR_GROUP_MATERIALS,
    "ball-stem-material": ATTR_GROUP_MATERIALS,
    "stem-seal": ATTR_GROUP_MATERIALS,
    "seat-seal": ATTR_GROUP_MATERIALS,
    "flow-disk": ATTR_GROUP_MATERIALS,
    "height-actuator": ATTR_GROUP_SIZE,
    "height-stem": ATTR_GROUP_SIZE,
    "valve-length": ATTR_GROUP_SIZE,
    "valve-od": ATTR_GROUP_SIZE,
    "center-to-edge": ATTR_GROUP_SIZE,
}


def group_key_for_slug(slug: str) -> str | None:
    """Return group key for an attribute slug, if known."""
    return DEFAULT_ATTR_GROUP_BY_SLUG.get(slug)


def attach_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add ``group`` / ``group_label`` to attribute API rows."""
    out: list[dict[str, Any]] = []
    for row in rows:
        slug = str(row.get("slug") or "")
        key = group_key_for_slug(slug)
        item = {**row}
        if key:
            item["group"] = key
            item["group_label"] = ATTR_GROUP_LABELS.get(key, key)
        out.append(item)
    return out


def group_attribute_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build ordered ``[{key, title, items}]`` for PDP category cards.

    Args:
        rows: Attribute API rows (with or without group fields).

    Returns:
        Non-empty groups in display order; ungrouped rows last.
    """
    tagged = attach_groups(rows)
    buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in ATTR_GROUP_ORDER}
    other: list[dict[str, Any]] = []
    for row in tagged:
        key = str(row.get("group") or "")
        if key in buckets:
            buckets[key].append(row)
        else:
            other.append(row)

    result: list[dict[str, Any]] = []
    for key in ATTR_GROUP_ORDER:
        items = buckets[key]
        if not items:
            continue
        result.append(
            {
                "key": key,
                "title": ATTR_GROUP_LABELS[key],
                "items": items,
            },
        )
    if other:
        result.append({"key": "other", "title": "Прочие", "items": other})
    return result
