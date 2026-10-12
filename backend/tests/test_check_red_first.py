"""scripts/check-red-first.py picks exactly the tests a change added or edited."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-red-first.py"

OLD = """
def helper():
    return 1


def test_kept():
    assert helper() == 1


def test_edited():
    assert 1 == 1


class TestGroup:
    def test_method(self):
        assert True
"""

NEW = """
def helper():
    return 2


def test_kept():
    assert helper() == 1


def test_edited():
    assert 2 == 2


def test_added():
    assert False


class TestGroup:
    def test_method(self):
        assert True

    def test_new_method(self):
        assert True
"""


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_red_first", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_selects_new_and_edited_tests_only() -> None:
    """A green-on-HEAD check over untouched tests would hide fitted tests."""
    red_first = _load()
    assert red_first.changed_tests(OLD, NEW) == ["test_edited", "test_added", "TestGroup::test_new_method"]


def test_new_file_selects_every_test() -> None:
    red_first = _load()
    assert red_first.changed_tests("", NEW) == [
        "test_kept",
        "test_edited",
        "test_added",
        "TestGroup::test_method",
        "TestGroup::test_new_method",
    ]


def test_moving_code_without_changing_it_selects_nothing() -> None:
    red_first = _load()
    assert red_first.changed_tests(OLD, "\n\n" + OLD) == []
