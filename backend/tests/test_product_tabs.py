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


def test_filter_analogs_bare_hoocon_headers_split_ds_dst() -> None:
    """Separate ``Hoocon …-DS`` / ``…-DST`` headings must not cross-leak."""
    text = """
Список аналогов SA30MU:

Hoocon SA30MU24-DS (24В)

– Belimo BEE24

Hoocon SA30MU24-DST (24 В с термодатчиком)

– Belimo BEE24ST
""".strip()
    out_ds = filter_analogs_for_sku(text, "SA30MU24-DS")
    assert "BEE24" in out_ds
    assert "BEE24ST" not in out_ds
    out_dst = filter_analogs_for_sku(text, "SA30MU24-DST")
    assert "BEE24ST" in out_dst
    assert "– Belimo BEE24\n" not in out_dst
    assert "– Belimo BEE24\r" not in out_dst
    assert not out_dst.rstrip().endswith("BEE24")


def test_filter_analogs_bare_hoocon_headers_split_by_control() -> None:
    """«Hoocon DA15FU24-D/DS» headings must not leak into A/AS editions."""
    text = """
Список аналогов для привода заслонки Hoocon серии DA15FU:

Hoocon DA15FU24-D/DS (24 В, 15Нм):

– Belimo BF24 — без пружины

Hoocon DA15FU24-A/AS (24 В, 15Нм с пружиной)

– Belimo BX24 — с пружиной

Hoocon DA15FU230-D/DS (230 В, 15Нм)

– Belimo BX230
""".strip()
    out_a = filter_analogs_for_sku(text, "DA15FU24-A")
    assert "BX24" in out_a
    assert "BF24" not in out_a
    assert "BX230" not in out_a
    assert "DA15FU24-A" in out_a
    assert "D/DS" not in out_a

    out_ds = filter_analogs_for_sku(text, "DA15FU24-DS")
    assert "BF24" in out_ds
    assert "BX24" not in out_ds
    assert "BX230" not in out_ds
    assert "DA15FU24-DS" in out_ds


def test_filter_analogs_hoocon_dlya_headers() -> None:
    """DAMU-style «Для Hoocon DA2MU230-…» blocks filter by edition + rewrite heading."""
    text = """
Список аналогов для привода серии DA..MU 2 Нм

Для Hoocon DA2MU230-DS/DA2MU230-AS (230В):

– Belimo CM230-L/R

Для Hoocon DA2MU24-D/DA2MU24-AS (24В)

– Belimo CM24-L/R

Основные характеристики аналогов

Крутящий момент: 2−5 Нм
""".strip()
    out_230 = filter_analogs_for_sku(text, "DA2MU230-A")
    assert "CM230-L/R" in out_230
    assert "CM24-L/R" not in out_230
    assert "Основные характеристики аналогов" in out_230
    assert "Для Hoocon DA2MU230-A (230В):" in out_230
    assert "DA2MU230-DS/DA2MU230-AS" not in out_230

    out_ds = filter_analogs_for_sku(text, "DA2MU230-DS")
    assert "CM230-L/R" in out_ds
    assert "Для Hoocon DA2MU230-DS (230В):" in out_ds
    assert "DA2MU230-AS" not in out_ds

    out_24 = filter_analogs_for_sku(text, "DA2MU24-DS")
    assert "CM24-L/R" in out_24
    assert "CM230-L/R" not in out_24
    assert "Для Hoocon DA2MU24-DS (24В)" in out_24


def test_filter_analogs_samu_voltage_headers() -> None:
    """SAMU «Аналоги 24В (SA…-DS/DST)» keeps one voltage and rewrites heading."""
    text = """
Список аналогов для привода заслонки Hoocon серии SA10MU:

Аналоги SA10MU24-DS/DST и SA10MU230-DS/DST:

Аналоги 24В (SA10MU24-DS/DST):

– Belimo EMF-24-10

Аналоги 230В (SA10MU230-DS/DST)

– Belimo EMF-230-10

Общие характеристики аналогов

Крутящий момент: 5-10 Нм
""".strip()
    out_24 = filter_analogs_for_sku(text, "SA10MU24-DS")
    assert "EMF-24-10" in out_24
    assert "EMF-230-10" not in out_24
    assert "Аналоги для SA10MU24-DS (24В):" in out_24
    assert "DS/DST" not in out_24
    assert "и SA10MU230" not in out_24
    assert "Общие характеристики аналогов" in out_24

    out_dst = filter_analogs_for_sku(text, "SA10MU230-DST")
    assert "EMF-230-10" in out_dst
    assert "EMF-24-10" not in out_dst
    assert "Аналоги для SA10MU230-DST (230В)" in out_dst


def test_filter_analogs_da4mu_per_control_and_voltage() -> None:
    """«Аналоги для DA4MU…-D/DS» vs «…-A/AS» keep only this SKU's block."""
    text = """
Список аналогов для привода заслонки Hoocon серии DA.MU 4Нм

Аналоги для DA4MU24-D/DS (24 В, 4Нм):

– Belimo LM24A-S (без возвратной пружины)

Аналоги для DA4MU230-D/DS (230 В, 4Нм)

– Belimo LM230A-S (без возвратной пружины)

Аналоги для DA4MU24-A/AS (24 В, 4Нм)

– AIRS LM24-SR

Аналоги для DA4MU230-A/AS (230 В, 4Нм)

– Dacond DAC-LMC230−04S

Все перечисленные модели:
Имеют крутящий момент 4Нм

Важно: При выборе аналога проверьте параметры.
""".strip()
    out_24_d = filter_analogs_for_sku(text, "DA4MU24-D")
    assert "LM24A-S" in out_24_d
    assert "LM230A-S" not in out_24_d
    assert "LM24-SR" not in out_24_d
    assert "DAC-LMC230" not in out_24_d
    assert "Все перечисленные" not in out_24_d
    assert "Важно:" in out_24_d
    assert "Аналоги для DA4MU24-D (24 В, 4Нм):" in out_24_d
    assert "D/DS" not in out_24_d

    out_230_a = filter_analogs_for_sku(text, "DA4MU230-AS")
    assert "DAC-LMC230" in out_230_a
    assert "LM24A-S" not in out_230_a
    assert "LM230A-S" not in out_230_a
    assert "LM24-SR" not in out_230_a
    assert "Все перечисленные" not in out_230_a
    assert "Аналоги для DA4MU230-AS (230 В, 4Нм)" in out_230_a
