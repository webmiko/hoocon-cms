"""Tests for catalog.etl.html_text — HTML → structured product copy."""

from __future__ import annotations

from catalog.etl.html_text import (
    clean_polluted_description,
    compose_product_description,
    extract_embedded_store_html,
    extract_product_text_blocks,
    extract_tilda_tabs,
    filter_analogs_for_sku,
    html_to_structured_text,
    html_to_text,
    is_noise_line,
)


def test_html_to_text_strips_tags() -> None:
    assert html_to_text("<p>Hello<br/>world</p>") == "Hello\nworld"
    assert html_to_text("") == ""
    assert html_to_text("   ") == ""


def test_html_to_structured_text_lists_and_sections() -> None:
    """Convert Tilda HTML lists into section titles and bullet lines."""
    raw = (
        "<strong>Общие характеристики:</strong><br />"
        "– Крутящий момент: 10 Нм<br />"
        "– Управление:<br />"
        "<ul>"
        '<li data-list="bullet"><strong>(D/DS)</strong> – открыто/закрыто</li>'
        '<li data-list="bullet"><strong>(A/AS)</strong> – плавное управление</li>'
        "</ul>"
        "– Площадь заслонки: до 1 м²"
    )
    text = html_to_structured_text(raw)
    assert "Общие характеристики:" in text
    assert "– Крутящий момент: 10 Нм" in text
    assert "Управление:" in text
    assert "– (D/DS) – открыто/закрыто" in text
    assert "<" not in text
    assert "class=" not in text


def test_compose_skips_legal_noise_and_keeps_store_descr() -> None:
    """Meta lead + store descr HTML become a clean card description."""
    descr = '<ul><li data-list="bullet">Диаметр: DN15</li><li data-list="bullet">Вид: 2-ходовый</li></ul>'
    text = compose_product_description(
        meta_description="Шаровые краны Hoocon DN15. Рабочее давление до 2.0 МПа.",
        html_blocks=[descr],
    )
    assert "Шаровые краны Hoocon DN15" in text
    assert "– Диаметр: DN15" in text
    assert "– Вид: 2-ходовый" in text


def test_clean_polluted_description_drops_chrome() -> None:
    """Strip leftover attribute fragments from a polluted scrape."""
    raw = (
        "Нормальный лид про привод 10 Нм.\n\n"
        '– label="Навигационное меню"\n'
        '– btnflex__text">Позвонить\n'
        "– Крутящий момент: 10 Нм\n"
    )
    cleaned = clean_polluted_description(raw)
    assert "Навигационное" not in cleaned
    assert "Позвонить" not in cleaned
    assert "– Крутящий момент: 10 Нм" in cleaned
    assert is_noise_line('label="Навигационное меню"')


def test_dedupe_description_lines_keeps_first() -> None:
    """Repeated bullets are collapsed."""
    from catalog.etl.html_text import dedupe_description_lines

    raw = "Лид.\n\n– Сечение провода: 0,5 мм²\n– Напряжение: 24 В\n– Сечение провода: 0,5 мм²\n"
    cleaned = dedupe_description_lines(raw)
    assert cleaned.count("Сечение провода") == 1
    assert "Напряжение: 24 В" in cleaned


def test_extract_embedded_store_html_from_json() -> None:
    """descr JSON with torque hint is extracted."""
    page = (
        r'{"descr":"<p>Крутящий момент 8 Нм для заслонки</p>",'
        r'"text":"<p>коротко</p>"}'
    )
    blocks = extract_embedded_store_html(page)
    assert blocks
    assert "момент" in html_to_text(blocks[0]).casefold()


def test_extract_product_text_blocks_ranks_specs() -> None:
    page = (
        '<div field="text">'
        "<p>Общие характеристики. Крутящий момент 10 Нм IP54.</p>"
        "</div>"
        '<div field="text">'
        "<p>Подготовка к установке. Монтаж привода. Инструменты.</p>"
        "</div>"
    )
    blocks = extract_product_text_blocks(page)
    assert blocks
    assert "момент" in html_to_text(blocks[0]).casefold()


def test_extract_tilda_tabs_maps_options_to_rec_blocks() -> None:
    html = """
    <select>
      <option value="111">Описание</option>
      <option value="222">Характеристики</option>
    </select>
    <div id="rec111" class="r">
    <div field="text"><p>Электропривод воздушной заслонки 8 Нм для ОВК систем.</p></div>
    </div>
    <div id="rec222" class="r">
    <div field="text"><p>Крутящий момент: 8 Нм. Степень защиты IP54 корпус привода.</p></div>
    </div>
    """
    tabs = extract_tilda_tabs(html)
    assert "description" in tabs
    assert "specs" in tabs
    assert "8 Нм" in tabs["specs"] or "момент" in tabs["specs"].casefold()
    assert extract_tilda_tabs("") == {}


def test_filter_analogs_for_sku_keeps_matching_block() -> None:
    text = """
Аналоги привода DA3FU24-DS
– Belimo LM24A-S
Аналоги привода DA3FU230-DS
– Belimo LM230A-S
"""
    out = filter_analogs_for_sku(text, "da3fu230-d")
    assert "LM230A" in out
    assert "LM24A" not in out
    assert filter_analogs_for_sku("", "x") == ""
    assert filter_analogs_for_sku(text, "") == text.strip()
