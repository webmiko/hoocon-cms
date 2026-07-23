"""Tests for DAFU-style instruction layout normalization."""

from __future__ import annotations

from catalog.etl.instruction_style import normalize_instruction_style


def test_drops_allcaps_banner_before_intro() -> None:
    text = normalize_instruction_style(
        "ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ:\n"
        "Инструкция по установке и управлению электропривода Hoocon DA..MU\n"
        "\n"
        "1. ПОДГОТОВКА К УСТАНОВКЕ:\n"
        "\n"
        "– Проверьте питание\n",
    )
    assert "ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ" not in text
    assert text.splitlines()[0].startswith("Инструкция по установке")
    assert "1. Подготовка к установке" in text
    assert "ПОДГОТОВКА" not in text


def test_blank_line_before_nested_heading() -> None:
    text = normalize_instruction_style(
        "2. Порядок установки\n\n– Закрепите привод\n2.2 Подключение электропитания\n\n– Используйте кабель\n",
    )
    lines = text.splitlines()
    idx = lines.index("2.2 Подключение электропитания")
    assert lines[idx - 1] == ""


def test_numbers_bare_smoke_sections_and_fixes_typos() -> None:
    text = normalize_instruction_style(
        "Инструкция SA..MU\n"
        "\n"
        "Подготовка к установке:\n"
        "\n"
        "– Убедитесь в наличиинеобходимых крепёжных элементов\n"
        "– Используйте провод сечением 0.5 мм²\n"
        "\n"
        "Монтаж привода\n"
        "\n"
        "– Закрепите привод\n",
    )
    assert "1. Подготовка к установке" in text
    assert "2. Монтаж привода" in text
    assert "наличии необходимых" in text
    assert "0,5 мм" in text
    assert "0.5" not in text


def test_nested_lowercase_title_capitalized() -> None:
    text = normalize_instruction_style(
        "3. Управление приводом\n\n3.2 пропорциональное (модулирующее) управление (0−10В)\n",
    )
    assert "3.2 Пропорциональное (модулирующее) управление (0−10В)" in text


def test_manual_procedure_steps_become_bullets() -> None:
    text = normalize_instruction_style(
        "Ручное управление:\n"
        "1. Вставьте шестигранный ключ в отверстие\n"
        "2. Поворачивайте ключ по/против часовой стрелки\n"
        "3. Доведите заслонку до нужного положения\n",
    )
    assert "1. Вставьте" not in text
    assert "– Вставьте шестигранный ключ в отверстие" in text
    assert "– Поворачивайте ключ по/против часовой стрелки" in text
    assert "– Доведите заслонку до нужного положения" in text
