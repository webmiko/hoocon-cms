"""Tests for canonical ТТХ label → slug mapping."""

from __future__ import annotations

from catalog.etl.label_to_slug import canonical_meta, label_to_slug


def test_label_to_slug_section_headers_skipped() -> None:
    """Bare section titles are noise unless they carry a value."""
    assert label_to_slug("Общие характеристики") is None
    assert label_to_slug("Управление") is None
    assert label_to_slug("Управление", value="2-/3-позиционное") == "control"
    assert label_to_slug("Сигнал обратной связи", value="0…10 В=") == ("feedback-signal")


def test_label_to_slug_power_disambiguation() -> None:
    """«Мощность» with Нм → moment; transformer / consumption kept."""
    assert label_to_slug("Мощность", value="10 Нм") == "moment"
    assert label_to_slug("Мощность трансформатора", value="18") == "transformer-va"
    assert label_to_slug("Потребляемая мощность", value="12 Вт") == ("power-consumption")
    assert label_to_slug("Мощность", value="") is None


def test_label_to_slug_voltage_and_ip() -> None:
    """Voltage aliases; IP in protection-class value → ip-rating."""
    assert label_to_slug("Напряжение") == "voltage"
    assert label_to_slug("Номинальное напряжение") == "voltage"
    assert label_to_slug("Класс защиты", value="IP54") == "ip-rating"
    assert label_to_slug("Класс защиты", value="III") == "protection-class"


def test_label_to_slug_dn_kvs_and_unknown() -> None:
    assert label_to_slug("DN") == "dn"
    assert label_to_slug("Kvs") == "kvs"
    # Avoid substrings like «вес» inside longer Russian words.
    assert label_to_slug("xyz-unknown-attr-qqq") is None
    assert label_to_slug("") is None


def test_canonical_meta_known_and_unknown() -> None:
    meta = canonical_meta("moment")
    assert meta is not None
    assert meta[0] == "Крутящий момент"
    assert meta[1] == "Нм"
    assert canonical_meta("no-such-slug") is None
