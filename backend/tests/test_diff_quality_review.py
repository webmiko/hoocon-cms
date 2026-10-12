"""TST001 in scripts/diff-quality-review.py: new tests must not assert on Python source text."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "diff-quality-review.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("diff_quality_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_flags_read_text_of_python_source() -> None:
    """Global review: 150 tests read .py text instead of calling the code."""
    review = _load()
    added = [
        (10, 'source = (ROOT / "crm" / "admin.py").read_text(encoding="utf-8")'),
        (11, 'assert "allowed_permissions" in source'),
    ]
    assert [lineno for lineno, _ in review.source_text_asserts(added)] == [10]


def test_flags_python_path_assigned_a_few_lines_above() -> None:
    review = _load()
    added = [
        (1, 'path = ROOT / "backend" / "cabinet" / "views.py"'),
        (2, "x = 1"),
        (3, 'text = path.read_text(encoding="utf-8")'),
    ]
    assert [lineno for lineno, _ in review.source_text_asserts(added)] == [3]


def test_allows_loaded_configs_and_marked_source_lint() -> None:
    review = _load()
    added = [
        (1, 'conf = (ROOT / "deploy" / "nginx" / "hoocon.conf").read_text()'),
        (2, 'data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))'),
        (3, 'etl = Path("series_copy_damu.py")'),
        (4, "text = etl.read_text()  # source-lint: shared constant instead of literal"),
    ]
    assert review.source_text_asserts(added) == []


def test_only_test_modules_are_scanned() -> None:
    review = _load()
    assert review.is_test_path("backend/tests/test_cabinet.py")
    assert review.is_test_path("backend/catalog/test_etl.py")
    assert not review.is_test_path("backend/cabinet/views.py")
    assert not review.is_test_path("backend/tests/fixtures/data.json")
