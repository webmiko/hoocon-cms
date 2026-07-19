"""Tests for Tilda product-tab extraction and analogs filtering."""

from __future__ import annotations

from catalog.etl.html_text import extract_tilda_tabs, filter_analogs_for_sku

SAMPLE_PAGE = """
<select class="t397__select">
  <option value="111">Описание</option>
  <option value="222">Инструкция</option>
  <option value="333">Характеристики</option>
  <option value="444">Аналоги</option>
</select>
<div id="rec111" class="r">
  <div field="title">Описание серии</div>
  <div field="text"><p>Общие сведения о серии.</p><ul><li>Пункт A</li></ul></div>
</div>
<div id="rec222" class="r">
  <div field="title">Инструкция</div>
  <div field="text"><p>Монтаж привода шаг 1.</p></div>
</div>
<div id="rec333" class="r">
  <div field="title">Технические характеристики</div>
  <div field="text"><p>Крутящий момент: 3 Нм</p></div>
</div>
<div id="rec444" class="r">
  <div field="text">
    <strong>Основные характеристики DA3FU230-DS:</strong>
    <p>230 В</p>
    <strong>Аналоги привода DA3FU230-DS:</strong>
    <ul><li>Belimo TF230-S</li></ul>
    <strong>Основные характеристики DA3FU24-DS:</strong>
    <p>24 В</p>
    <strong>Аналоги привода DA3FU24-DS:</strong>
    <ul><li>Belimo TF24-S</li></ul>
  </div>
</div>
<div id="rec999" class="r">footer</div>
"""


def test_extract_tilda_tabs_four_sections() -> None:
    """All four product tabs are extracted as structured text."""
    tabs = extract_tilda_tabs(SAMPLE_PAGE)
    assert "description" in tabs and "серии" in tabs["description"].casefold()
    assert "instructions" in tabs and "Монтаж" in tabs["instructions"]
    assert "specs" in tabs and "3 Нм" in tabs["specs"]
    assert "analogs" in tabs and "Belimo" in tabs["analogs"]


def test_filter_analogs_keeps_matching_edition() -> None:
    """Analog blocks for the other voltage edition are dropped."""
    tabs = extract_tilda_tabs(SAMPLE_PAGE)
    out = filter_analogs_for_sku(tabs["analogs"], "da3fu230-ds")
    assert "TF230-S" in out
    assert "TF24-S" not in out
    assert "230" in out
