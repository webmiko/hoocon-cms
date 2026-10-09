"""scripts/security-hotspot-check.sh: dangerouslySetInnerHTML только с DOMPurify.

ArticlePage очищает HTML один раз до оглавления и рендерит ``bodyWithToc.html`` —
проверка требовала ``sanitizeHtml(`` в той же строке и валила checkup, хотя
значение уже очищено. Неочищенная переменная по-прежнему должна падать.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "security-hotspot-check.sh"
OK_LINE = "✓ frontend: dangerouslySetInnerHTML только с sanitizeHtml()"


def _run_in_repo(tmp_path: Path, tsx: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "src" / "Page.tsx").write_text(tsx, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return subprocess.run(["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False)


def test_variable_sanitized_before_toc_passes(tmp_path: Path) -> None:
    result = _run_in_repo(
        tmp_path,
        "  const bodyWithToc = extractArticleToc(sanitizeHtml(article.body));\n"
        "  <div dangerouslySetInnerHTML={{ __html: bodyWithToc.html }} />\n",
    )
    assert OK_LINE in result.stdout
    assert result.returncode == 0


def test_unsanitized_variable_still_fails(tmp_path: Path) -> None:
    result = _run_in_repo(
        tmp_path,
        "  const bodyWithToc = extractArticleToc(article.body);\n"
        "  <div dangerouslySetInnerHTML={{ __html: bodyWithToc.html }} />\n",
    )
    assert "Page.tsx:2:" in result.stdout
    assert "нужна санитизация" in result.stdout
    assert result.returncode == 1


def test_inline_sanitize_passes(tmp_path: Path) -> None:
    result = _run_in_repo(tmp_path, "  <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(page.body) }} />\n")
    assert OK_LINE in result.stdout


def test_article_page_render_value_comes_from_sanitize_html() -> None:
    src = (ROOT / "frontend" / "src" / "pages" / "ArticlePage.tsx").read_text(encoding="utf-8")
    assert "const bodyWithToc = extractArticleToc(sanitizeHtml(article.body));" in src
    assert "__html: bodyWithToc.html" in src
