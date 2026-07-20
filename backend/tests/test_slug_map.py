"""Tests for Tilda UID → SEO slug mapping from store CSV."""

from __future__ import annotations

from pathlib import Path

from catalog.etl.slug_map import (
    apply_slug_to_product,
    build_uid_slug_map,
    load_tproduct_slug_map,
    slug_from_url,
)


def test_load_tproduct_slug_map(tmp_path: Path) -> None:
    """Seed CSV maps /tproduct/<uid> → canonical ЧПУ."""
    seed = tmp_path / "seed.csv"
    seed.write_text(
        "from_path,to_path\n/tproduct/12345,/sharovoy-kran-bv215\n/other/path,/ignored\n",
        encoding="utf-8",
    )
    mapping = load_tproduct_slug_map(seed)
    assert mapping["12345"] == "sharovoy-kran-bv215"
    assert "other" not in mapping


def test_load_tproduct_slug_map_missing_file(tmp_path: Path) -> None:
    assert load_tproduct_slug_map(tmp_path / "nope.csv") == {}


def test_slug_from_url_chpu_and_tproduct() -> None:
    """ЧПУ path returned as-is; tproduct resolved via map."""
    assert slug_from_url("https://hoocon.ru/privod-da8mqu", {}) == "privod-da8mqu"
    assert slug_from_url("", {}) is None
    assert slug_from_url("https://hoocon.ru/", {}) is None
    tmap = {"999": "from-seed"}
    assert slug_from_url("https://hoocon.ru/tproduct/999", tmap) == "from-seed"
    assert slug_from_url("https://hoocon.ru/tproduct/111", tmap) is None


def test_build_uid_slug_map_uses_parent_rows_only(tmp_path: Path) -> None:
    """Empty SKU = parent product; non-empty SKU editions are skipped."""
    seed = tmp_path / "seed.csv"
    seed.write_text(
        "from_path,to_path\n/tproduct/42,/resolved-from-seed\n",
        encoding="utf-8",
    )
    store = tmp_path / "store.csv"
    store.write_text(
        (
            "Tilda UID;External ID;SKU;Url;Title\n"
            "uid-parent;;;https://hoocon.ru/sharovoy-kran-bv215;Parent\n"
            "uid-edition;ext-1;8100-bv215a;https://hoocon.ru/edition-only;Edition\n"
            "uid-tproduct;;;https://hoocon.ru/tproduct/42;Needs seed\n"
        ),
        encoding="utf-8",
    )
    mapping = build_uid_slug_map(seed_csv=seed, store_csv=store)
    assert mapping["uid-parent"] == "sharovoy-kran-bv215"
    assert "uid-edition" not in mapping
    assert "ext-1" not in mapping
    assert mapping["uid-tproduct"] == "resolved-from-seed"


def test_build_uid_slug_map_without_store(tmp_path: Path) -> None:
    seed = tmp_path / "seed.csv"
    seed.write_text(
        "from_path,to_path\n/tproduct/1,/only-seed\n",
        encoding="utf-8",
    )
    assert build_uid_slug_map(seed_csv=seed) == {"1": "only-seed"}
    assert build_uid_slug_map(seed_csv=seed, store_csv=tmp_path / "x.csv") == {
        "1": "only-seed",
    }


def test_apply_slug_to_product_fills_missing_buttonlink() -> None:
    raw = {"uid": "u1", "title": "X"}
    patched = apply_slug_to_product(raw, {"u1": "my-slug"})
    assert patched["buttonlink"] == "/my-slug"
    assert raw.get("buttonlink") is None
    assert apply_slug_to_product({"uid": "u1", "buttonlink": "/keep"}, {})["buttonlink"] == "/keep"
    assert apply_slug_to_product({"uid": "missing"}, {"u1": "x"}) == {"uid": "missing"}
