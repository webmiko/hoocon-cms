"""Tests for Tilda UID → SEO slug mapping from store CSV."""

from __future__ import annotations

from pathlib import Path

from catalog.etl.slug_map import build_uid_slug_map


def test_build_uid_slug_map_uses_parent_rows_only(tmp_path: Path) -> None:
    """Empty SKU = parent product; non-empty SKU editions are skipped."""
    seed = tmp_path / "seed.csv"
    seed.write_text("from_path,to_path\n", encoding="utf-8")
    store = tmp_path / "store.csv"
    store.write_text(
        (
            "Tilda UID;External ID;SKU;Url;Title\n"
            "uid-parent;;;https://hoocon.ru/sharovoy-kran-bv215;Parent\n"
            "uid-edition;ext-1;8100-bv215a;https://hoocon.ru/edition-only;Edition\n"
        ),
        encoding="utf-8",
    )
    mapping = build_uid_slug_map(seed_csv=seed, store_csv=store)
    assert mapping["uid-parent"] == "sharovoy-kran-bv215"
    assert "uid-edition" not in mapping
    assert "ext-1" not in mapping
