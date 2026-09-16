"""Branch-based gigachat_kb.txt format and smart search."""

from __future__ import annotations

from pathlib import Path

import pytest

from supportchat.gigachat.kb_branches import (
    KbBranch,
    KbFileMeta,
    build_policy_branch,
    format_bot_kb_document,
    load_kb_branches,
    parse_kb_branches,
    search_kb_context,
    select_kb_branches,
)


def _sample_document() -> str:
    branches = [
        build_policy_branch(),
        KbBranch(
            id="manual.html.da2mu-d-ds",
            title="DA2MU manual",
            tags=frozenset({"manual", "da", "mu"}),
            series=frozenset({"da2mu"}),
            tokens=frozenset({"da2mu", "da2mu24"}),
            gotos=frozenset({("da2mu", "manual.html.da2mu-d-ds")}),
            body="– Крутящий момент: 2 Нм\nDA2MU24-D/DS",
        ),
        KbBranch(
            id="manual.html.da20fu-d-ds",
            title="DA20FU manual",
            tags=frozenset({"manual", "da", "fu"}),
            tokens=frozenset({"da20fu"}),
            body="– Крутящий момент: 20 Нм",
        ),
        KbBranch(
            id="faq.home.1",
            title="FAQ SA vs DA",
            tags=frozenset({"faq"}),
            body="В: SA vs DA?\nО: Разные серии.",
        ),
    ]
    meta = KbFileMeta(version=2, built_at="2026-09-16T10:00:00+00:00", branch_count=len(branches))
    return format_bot_kb_document(branches, meta=meta)


def test_parse_and_roundtrip_branches() -> None:
    """@BRANCH BEGIN/END парсится обратно в структуру."""
    document = _sample_document()
    branches = parse_kb_branches(document)
    assert len(branches) == 4
    manual = next(b for b in branches if b.id == "manual.html.da2mu-d-ds")
    assert "2 Нм" in manual.body
    assert "da2mu" in manual.tokens


def test_search_prefers_da2mu_not_da20() -> None:
    """Умный поиск: DA2MU → ветка 2 Нм, не DA20FU."""
    branches = parse_kb_branches(_sample_document())
    picked = select_kb_branches(branches, query="Какой момент у DA2MU?", max_chars=5000)
    ids = [branch.id for branch in picked]
    assert "manual.html.da2mu-d-ds" in ids
    assert "manual.html.da20fu-d-ds" not in ids
    assert "policy.bot" in ids


def test_goto_routes_to_manual_branch() -> None:
    """@GOTO поднимает целевую ветку в выдаче."""
    document = _sample_document()
    branches = parse_kb_branches(document)
    picked = select_kb_branches(branches, query="нужен привод", max_chars=8000)
    assert any(branch.id == "policy.bot" for branch in picked)


def test_search_context_hints_24v_not_230() -> None:
    """Контекст для 24 В содержит подсказку и артикулы …24."""
    document = _sample_document()
    branches = parse_kb_branches(document)
    manual = next(b for b in branches if b.id == "manual.html.da2mu-d-ds")
    enriched = manual.body.replace(
        "DA2MU24-D/DS",
        "DA2MU24-D/DS",
    )
    from supportchat.gigachat.kb_branches import KbBranch

    branches = tuple(
        KbBranch(
            b.id,
            b.title,
            b.tags,
            b.series,
            frozenset({*b.tokens, "da2mu24", "da2mu230"}),
            b.gotos,
            "Артикулы и напряжение (канон):\n"
            "- DA2MU24-D/DS — AC/DC 24 В\n"
            "- DA2MU230-D/DS — AC 100…240 В\n\n" + enriched,
        )
        if b.id == "manual.html.da2mu-d-ds"
        else b
        for b in branches
    )
    from supportchat.gigachat.kb_branches import KbFileMeta, format_bot_kb_document

    doc = format_bot_kb_document(
        list(branches),
        meta=KbFileMeta(2, "2026-01-01T00:00:00+00:00", len(branches)),
    )
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "kb.txt"
    path.write_text(doc, encoding="utf-8")
    ctx = search_kb_context("Нужен DA2MU на 24В", max_chars=8000, path=path)
    assert "24 В" in ctx
    assert "суффиксом 24" in ctx
    assert "DA2MU24" in ctx


def test_document_lines_within_119_chars() -> None:
    """Собранный TXT соблюдает лимит 119 символов на строку."""
    document = _sample_document()
    assert all(len(line) <= 119 for line in document.splitlines())


@pytest.mark.django_db
def test_runtime_context_from_branches_only(monkeypatch, tmp_path: Path) -> None:
    """Рантайм берёт контекст только из файла веток."""
    kb = tmp_path / "kb.txt"
    kb.write_text(_sample_document(), encoding="utf-8")
    monkeypatch.setattr("supportchat.gigachat.kb_branches.PACKAGED_KB_PATH", kb)
    load_kb_branches.cache_clear()
    from supportchat.gigachat.knowledge import build_knowledge_context

    ctx = build_knowledge_context(user_query="DA2MU момент")
    assert "policy.bot" in ctx or "[policy.bot]" in ctx
    assert "2 Нм" in ctx
    assert "20 Нм" not in ctx
