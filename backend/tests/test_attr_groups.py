"""Tests for PDP ТТХ attribute grouping / Y–U pairing."""

from __future__ import annotations

from catalog.etl.attr_groups import (
    ATTR_GROUP_ELECTRICAL,
    group_attribute_rows,
    order_group_items,
)


def test_order_group_items_keeps_yu_adjacent_on_even_index() -> None:
    """Y then U must sit on one 2-column row (even start index)."""
    rows = [
        {"slug": "voltage", "name": "Напряжение", "value": "24 В"},
        {"slug": "wire-cross-section", "name": "Сечение", "value": "0,5"},
        {"slug": "power-consumption", "name": "Мощность", "value": "3 Вт"},
        {
            "slug": "feedback-signal-u",
            "name": "Обратная связь U",
            "value": "0…10 В=",
        },
        {
            "slug": "control-signal-y",
            "name": "Управляющий сигнал Y",
            "value": "0…10 В=",
        },
        {"slug": "aux-switch", "name": "Вспом. переключатель", "value": "Нет"},
    ]
    ordered = order_group_items(rows)
    slugs = [r["slug"] for r in ordered]
    yi = slugs.index("control-signal-y")
    ui = slugs.index("feedback-signal-u")
    assert ui == yi + 1
    assert yi % 2 == 0


def test_group_attribute_rows_puts_legacy_yu_in_electrical() -> None:
    """H8205 aliases control-signal-y / feedback-signal-u → electrical."""
    rows = [
        {"slug": "material", "name": "Материал", "value": "Чугун"},
        {
            "slug": "control-signal-y",
            "name": "Упр. сигнал Y",
            "value": "0…10 В=",
        },
        {
            "slug": "feedback-signal-u",
            "name": "Обратная связь U",
            "value": "0…10 В=",
        },
        {"slug": "voltage", "name": "Напряжение", "value": "230 В"},
    ]
    groups = group_attribute_rows(rows)
    by_key = {g["key"]: g for g in groups}
    assert ATTR_GROUP_ELECTRICAL in by_key
    elec_slugs = [r["slug"] for r in by_key[ATTR_GROUP_ELECTRICAL]["items"]]
    assert elec_slugs.index("control-signal-y") + 1 == elec_slugs.index(
        "feedback-signal-u",
    )
    assert "material" not in elec_slugs
