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

# Y/U signal slugs (canonical + legacy ETL aliases on H8205 / DAMU).
CONTROL_SIGNAL_SLUGS = frozenset({"control-signal", "control-signal-y"})
FEEDBACK_SIGNAL_SLUGS = frozenset({"feedback-signal", "feedback-signal-u"})

# Preferred order inside a group (unknown slugs keep relative order at end).
_ATTR_SLUG_ORDER: tuple[str, ...] = (
    "voltage",
    "voltage-range",
    "power-consumption",
    "transformer-va",
    "wire-cross-section",
    "control",
    "control-signal",
    "control-signal-y",
    "feedback-signal",
    "feedback-signal-u",
    "aux-switch",
    "fault-alarm",
    "moment",
    "damper-area",
    "running-time",
    "rotation-angle",
    "rotation-direction",
    "manual-override",
    "noise",
    "position-indication",
    "temp-sensor",
    "terminal-size",
    "protection-class",
    "ip-rating",
    "ambient-temp",
    "storage-temp",
    "humidity",
    "medium",
    "media-temp",
    "dn",
    "ways",
    "thread",
    "connection",
    "kvs",
    "diff-pressure",
    "material",
)

_ATTR_SLUG_RANK: dict[str, int] = {slug: i for i, slug in enumerate(_ATTR_SLUG_ORDER)}

# Default slug → group for catalog (actuators + valves).
DEFAULT_ATTR_GROUP_BY_SLUG: dict[str, str] = {
    "voltage": ATTR_GROUP_ELECTRICAL,
    "voltage-range": ATTR_GROUP_ELECTRICAL,
    "power-consumption": ATTR_GROUP_ELECTRICAL,
    "transformer-va": ATTR_GROUP_ELECTRICAL,
    "wire-cross-section": ATTR_GROUP_ELECTRICAL,
    "control-signal": ATTR_GROUP_ELECTRICAL,
    "control-signal-y": ATTR_GROUP_ELECTRICAL,
    "feedback-signal": ATTR_GROUP_ELECTRICAL,
    "feedback-signal-u": ATTR_GROUP_ELECTRICAL,
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
    "flange-pcd-pn16": ATTR_GROUP_SIZE,
    "flange-bolts-pn16": ATTR_GROUP_SIZE,
    "flange-od-pn16": ATTR_GROUP_SIZE,
    "flange-pcd-pn25": ATTR_GROUP_SIZE,
    "flange-bolts-pn25": ATTR_GROUP_SIZE,
    "flange-od-pn25": ATTR_GROUP_SIZE,
    "flange-face": ATTR_GROUP_SIZE,
}


def group_key_for_slug(slug: str) -> str | None:
    """Return group key for an attribute slug, if known."""
    return DEFAULT_ATTR_GROUP_BY_SLUG.get(slug)


def _is_control_signal_row(row: dict[str, Any]) -> bool:
    slug = str(row.get("slug") or "")
    if slug in CONTROL_SIGNAL_SLUGS:
        return True
    name = str(row.get("name") or "").casefold()
    return "сигнал" in name and "y" in name and "обратн" not in name


def _is_feedback_signal_row(row: dict[str, Any]) -> bool:
    slug = str(row.get("slug") or "")
    if slug in FEEDBACK_SIGNAL_SLUGS:
        return True
    name = str(row.get("name") or "").casefold()
    return "обратная связь" in name


def order_group_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort ТТХ cards; keep Y then U adjacent on an even grid index.

    Wide PDP uses a 2-column spec grid — the Y/U pair must start on an even
    index so both sit on the same row.

    Args:
        items: Attribute rows for one group (mutated order only).

    Returns:
        New list with preferred slug order and Y/U paired.
    """
    if len(items) < 2:
        return list(items)

    y_rows = [row for row in items if _is_control_signal_row(row)]
    u_rows = [row for row in items if _is_feedback_signal_row(row)]
    rest = [row for row in items if not _is_control_signal_row(row) and not _is_feedback_signal_row(row)]

    def slug_key(row: dict[str, Any]) -> tuple[int, int, str]:
        slug = str(row.get("slug") or "")
        rank = _ATTR_SLUG_RANK.get(slug)
        if rank is None:
            return (1, 0, slug)
        return (0, rank, slug)

    rest_sorted = sorted(rest, key=slug_key)
    pair = y_rows + u_rows
    if not pair:
        return rest_sorted

    # Place Y/U after «Управление» when present; else after voltage block; else end.
    insert_at = len(rest_sorted)
    for i, row in enumerate(rest_sorted):
        slug = str(row.get("slug") or "")
        if slug == "control":
            insert_at = i + 1
            break
    else:
        for i, row in enumerate(rest_sorted):
            slug = str(row.get("slug") or "")
            if slug in {"voltage", "voltage-range", "wire-cross-section"}:
                insert_at = i + 1

    out = rest_sorted[:insert_at] + pair + rest_sorted[insert_at:]

    # Shift pair to even index so 2-column CSS grid keeps Y|U on one row.
    pair_start = insert_at
    if pair_start % 2 == 1 and pair_start > 0:
        prev = out.pop(pair_start - 1)
        # After pop, pair starts at pair_start - 1; append prev after the pair.
        out.insert(pair_start - 1 + len(pair), prev)

    return out


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
                "items": order_group_items(items),
            },
        )
    if other:
        result.append(
            {
                "key": "other",
                "title": "Прочие",
                "items": order_group_items(other),
            },
        )
    return result
