"""Tests for DA..MU series copy helpers."""

from __future__ import annotations

from catalog.etl.series_copy_damu import instructions_for_damu_sku


def test_instructions_for_damu_sku_scopes_voltage_and_aux() -> None:
    """24 В -D omits 230 В and auxiliary-switch chapter."""
    text = instructions_for_damu_sku("DA4MU24-D")
    assert text is not None
    assert "Hoocon DA4MU" in text
    assert "AC/DC 24 В" in text
    assert "100…240" not in text
    assert "Исполнения 230" not in text
    assert "Вспомогательные переключатели" not in text
    assert "84,8 × 145,6 × 65" in text
    assert "круглый 6…16 мм / квадратный 8×8…12×12 мм" in text


def test_instructions_for_damu_sku_modulating_with_aux() -> None:
    """230 В -AS keeps proportional + aux chapters only for that edition."""
    text = instructions_for_damu_sku("DA4MU230-AS")
    assert text is not None
    assert "AC 100…240 В" in text
    assert "AC/DC 24 В" not in text
    assert "Пропорциональное управление" in text
    assert "Вспомогательные переключатели" in text
    assert "клеммы 21,22" in text
    assert "Переключатель b" in text
    assert "DIP-переключатели" in text
    assert "Двухпозиционное управление" not in text
    assert "0(4)...20 мА (спецзаказ)" in text
    assert "по схеме в инструкции" not in text
    assert "по заводской таблице в инструкции" not in text


def test_instructions_for_damu_sku_on_off_aux_omits_dip() -> None:
    """-DS gets aux angle table without modulating DIP section."""
    text = instructions_for_damu_sku("DA2MU24-DS")
    assert text is not None
    assert "Вспомогательные переключатели" in text
    assert "клеммы 21,22" in text
    assert "Переключатель b" not in text
    assert "DIP-переключатели" not in text


_MANUAL_SWITCH_A = (
    "– 0–10°: клеммы 21,22 замкнуто / клеммы 21,23 разомкнуто.",
    "– 10–90°: клеммы 21,22 разомкнуто / клеммы 21,23 замкнуто.",
)
_MANUAL_SWITCH_B = (
    "– 0–80°: клеммы 24,25 разомкнуто / клеммы 24,26 замкнуто.",
    "– 80–90°: клеммы 24,25 замкнуто / клеммы 24,26 разомкнуто.",
)


def _switch_rows(text: str, header: str) -> list[str]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    return lines[start + 1 : start + 3]


def test_damu_aux_switch_table_matches_ru_manual() -> None:
    """Regression: 0–80° sat under switch a and b was «аналогично a»."""
    text = instructions_for_damu_sku("DA8MU24-AS")
    assert text is not None
    assert tuple(_switch_rows(text, "– Переключатель a")) == _MANUAL_SWITCH_A
    assert tuple(_switch_rows(text, "– Переключатель b")) == _MANUAL_SWITCH_B
    assert "аналогично" not in text
    assert "0–80°: клеммы 21" not in text


def test_damu_series_instructions_carry_both_switch_tables() -> None:
    from catalog.etl.series_copy_damu import SERIES_INSTRUCTIONS

    for row in (*_MANUAL_SWITCH_A, *_MANUAL_SWITCH_B):
        assert row in SERIES_INSTRUCTIONS
    assert "аналогично переключателю a" not in SERIES_INSTRUCTIONS


def test_damu_specs_match_ru_manual_shaft_and_feedback() -> None:
    """Regression: DA2/4/6 shaft «8…16» and DIP feedback «0(4)…10 мА»."""
    from catalog.etl.series_copy_damu import TORQUE_SPECS

    assert TORQUE_SPECS[2]["shaft-diameter"] == "круглый 6…16 мм / квадратный 5×5…12×12 мм"
    for nm in (4, 6):
        assert TORQUE_SPECS[nm]["shaft-diameter"] == "круглый 6…16 мм / квадратный 8×8…12×12 мм"
    text = instructions_for_damu_sku("DA8MU24-AS")
    assert text is not None
    assert "ON — 0(4)...20 мА." in text
    assert "10 мА" not in text


def test_instructions_for_damu_sku_rejects_other_series() -> None:
    assert instructions_for_damu_sku("DA5FU24-D") is None
    assert instructions_for_damu_sku("") is None
