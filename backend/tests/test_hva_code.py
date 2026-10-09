"""One HVA code parser (M48).

Before: five regexes disagreed — the diagram ETL ignored 5UQ / 8Q (no
dimensions crop, no envelope) and kept its own envelope table.
"""

from __future__ import annotations

import re

import pytest

from catalog.docs_hub import doc_family_key
from catalog.etl.manual_diagrams import hva_catalog_page_key, parse_hva_series
from catalog.etl.manual_pdfs import sku_codes_for_hva_manual
from catalog.etl.series_copy_hva import CATALOG_FAMILIES, FAMILY_SPECS
from catalog.etl.sku_variant import HVA_CODE_SQL_PATTERN, parse_hva_code, parse_sku_variant


@pytest.mark.parametrize(
    ("code", "voltage", "aux", "nm", "suffix"),
    [
        ("HVA24-5", "24", False, 5, ""),
        ("HVA230S-5Q", "230", True, 5, "q"),
        ("hva24-5uq", "24", False, 5, "uq"),
        ("HVA24S-8Q", "24", True, 8, "q"),
        ("HVA230-10QX", "230", False, 10, "qx"),
        ("HVA24-5P", "24", False, 5, "p"),
    ],
)
def test_parse_hva_code(code: str, voltage: str, aux: bool, nm: int, suffix: str) -> None:
    hva = parse_hva_code(code)
    assert hva is not None
    assert (hva.voltage, hva.aux, hva.nm, hva.suffix) == (voltage, aux, nm, suffix)


@pytest.mark.parametrize("code", ["HVD24-5", "HVA-5", "HVA12-5", "HVA24-5X", "DA5FU24-D", ""])
def test_parse_hva_code_rejects_other_codes(code: str) -> None:
    assert parse_hva_code(code) is None


def test_every_catalog_family_gets_a_dimensions_page() -> None:
    """5UQ / 8Q / 2 Нм share a housing drawing instead of being skipped."""
    for nm, speed in CATALOG_FAMILIES:
        hva = parse_hva_code(f"HVA24-{nm}{speed}")
        assert hva is not None
        assert hva_catalog_page_key(hva) is not None, hva.family
        assert "dimensions" in FAMILY_SPECS[(nm, speed)]


def test_shared_housing_page_matches_envelope() -> None:
    for code, page in (("HVA24-5UQ", (10, True)), ("HVA24-8Q", (10, True)), ("HVA24-2", (5, False))):
        hva = parse_hva_code(code)
        assert hva is not None
        assert hva_catalog_page_key(hva) == page
        own = FAMILY_SPECS[(hva.nm, hva.suffix)]["dimensions"]
        housing = FAMILY_SPECS[(page[0], "q" if page[1] else "")]["dimensions"]
        assert own == housing


def test_callers_agree_on_families() -> None:
    assert parse_hva_series("HVA24-5UQ") is None
    assert parse_hva_series("HVA230S-5Q") == (5, True)
    assert doc_family_key("HVA24-5UQ") == "HVA-5UQ"
    assert doc_family_key("HVA24-10QX") == "HVA-10QX"
    assert sku_codes_for_hva_manual("5uq", ["HVA24-5UQ", "HVA24-5Q", "HVA24-5QX"]) == ["HVA24-5UQ"]
    variant = parse_sku_variant("hva24s-8q")
    assert (variant.control, variant.aux_switch) == ("modulating", True)


@pytest.mark.parametrize("code", ["hva24-5", "hva230s-5uq", "hva24-10qx", "hva24-5p", "hvd24-5", "hva24-5x"])
def test_sql_pattern_matches_parser(code: str) -> None:
    """``HVA_CODE_SQL_PATTERN`` (Postgres iregex) accepts exactly what the parser does."""
    sql_match = re.fullmatch(HVA_CODE_SQL_PATTERN, code, re.I) is not None
    assert sql_match == (parse_hva_code(code) is not None)
