"""Manual extraction helpers and packaged KB build."""

from __future__ import annotations

from pathlib import Path

import pytest

from supportchat.gigachat.kb_branches import load_kb_branches, parse_bot_kb_meta
from supportchat.gigachat.kb_build import write_packaged_kb
from supportchat.gigachat.kb_text import ManualChunk
from supportchat.gigachat.manuals_kb import (
    extract_manual_html_text,
    extract_manual_pdf_text,
    extract_sku_tokens,
    extract_voltage_hint,
    select_manual_chunks,
)


def test_extract_manual_html_text_from_stage(tmp_path: Path) -> None:
    """HTML-мануал: текст из .stage без CSS/JS."""
    html = """<!DOCTYPE html><html><head><title>DA2MU test</title>
    <style>body{color:red}</style></head><body>
    <div class="stage"><h2>Технические характеристики</h2>
    <p>Крутящий момент: 2 Нм</p><p>IP54</p></div>
    <script>alert(1)</script></body></html>"""
    path = tmp_path / "da2mu-d-ds.html"
    path.write_text(html, encoding="utf-8")
    text = extract_manual_html_text(path, max_chars=2000)
    assert "2 Нм" in text
    assert "IP54" in text
    assert "color:red" not in text
    assert text.index("2 Нм") < text.index("IP54")


def test_write_and_load_branch_kb(tmp_path: Path) -> None:
    """Сборка TXT с @BRANCH и загрузка веток."""
    ru = tmp_path / "manuals-ru"
    da = ru / "DA"
    da.mkdir(parents=True)
    (da / "da5fu-d-ds.html").write_text(
        "<html><body><div class='stage'><p>DA5FU 5 Нм HVAC</p></div></body></html>",
        encoding="utf-8",
    )
    pdf_root = tmp_path / "pdf" / "RU"
    pdf_root.mkdir(parents=True)

    out = tmp_path / "kb.txt"
    write_packaged_kb(out, manuals_ru_dir=ru, manuals_pdf_dir=pdf_root.parent, include_site=False)
    load_kb_branches.cache_clear()
    branches = load_kb_branches(out)
    meta = parse_bot_kb_meta(out.read_text(encoding="utf-8"))
    assert meta is not None
    assert meta.version == 2
    manual = [b for b in branches if b.id.startswith("manual.")]
    assert len(manual) == 1
    assert "DA5FU" in manual[0].body


def test_select_manual_chunks_by_query() -> None:
    """Подбор мануала по артикулу (unit-level helper)."""
    chunks = (
        ManualChunk("html", "_manuals-ru/DA/da2mu-d-ds.html", "DA2MU 2 Нм"),
        ManualChunk("html", "_manuals-ru/DA/da5fu-d-ds.html", "DA5FU 5 Нм пружина"),
    )
    picked = select_manual_chunks(chunks, query="Нужен DA5FU на 230В", max_chars=5000)
    assert picked[0].label.endswith("da5fu-d-ds.html")


def test_extract_sku_tokens_normalizes_mu_spacing() -> None:
    """DA 2 MU и DA2MU дают один токен серии."""
    assert extract_sku_tokens("Какой момент у DA 2 MU?") == ("da2mu",)
    assert extract_sku_tokens("DA4MU и DA6MU") == ("da4mu", "da6mu")


def test_extract_sku_tokens_with_voltage_suffix() -> None:
    """24 В в вопросе добавляет токен da2mu24, не путая с 230."""
    assert extract_voltage_hint("Нужен DA2MU на 24В") == "24"
    assert "da2mu24" in extract_sku_tokens("Нужен DA2MU на 24В")
    assert extract_voltage_hint("DA2MU 230В") == "230"
    assert "da2mu230" in extract_sku_tokens("DA2MU 230В")


def test_extract_manual_pdf_text_empty_on_missing(tmp_path: Path) -> None:
    """Битый PDF не роняет сборку."""
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    assert extract_manual_pdf_text(path) == ""


@pytest.mark.skipif(
    not Path(__file__).resolve().parents[2].joinpath("_manuals-ru", "DA").is_dir(),
    reason="локальные _manuals-ru не подключены",
)
def test_build_command_writes_repo_kb(tmp_path: Path) -> None:
    """Интеграция: полная сборка из репозитория."""
    out = tmp_path / "full.txt"
    write_packaged_kb(out, include_site=False)
    text = out.read_text(encoding="utf-8")
    assert "@BRANCH BEGIN" in text
    load_kb_branches.cache_clear()
    branches = load_kb_branches(out)
    assert len([b for b in branches if b.id.startswith("manual.")]) > 10
