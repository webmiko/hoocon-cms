"""Tests for BV* ball-valve series copy (CSV → cards)."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

from catalog.etl.label_to_slug import label_to_slug
from catalog.etl.series_copy_ball_valves import (
    BallValveSeries,
    _diff_pressure_mpa,
    _drive_families_from_mods,
    apply_series_enrichment,
    format_bracket,
    format_compatible_actuators,
    kvs_for_sku,
    load_ball_valve_series,
    product_slug_for_series,
)
from catalog.etl.series_copy_bv215 import kvs_for_sku_code
from catalog.models import (
    SKU,
    AttributeValue,
    Category,
    Product,
    ProductImage,
)


def test_kvs_for_sku_code_editions() -> None:
    """Edition letters a–e map to Tilda Kvs values for BV215."""
    assert kvs_for_sku_code("8100-bv215a") == "1,6"
    assert kvs_for_sku_code("8100-BV215E") == "10,1"
    assert kvs_for_sku_code("8100-bv220a") is None


def test_kvs_for_sku_matches_full_series_number() -> None:
    """BV prefix strip compares full 3-digit series (BV215 → «215», not «15»)."""
    series = BallValveSeries(
        code="BV215",
        product_slug="sharovoy-kran-bv215",
        product_name="BV215",
        ways="2-ходовый",
        dn="15",
        thread="внутренняя G 1/2",
        drive_series=("DA5MU24",),
        gallery_urls=(),
        kvs_by_edition={"a": "1,6", "e": "10,1"},
        height_actuator="",
        height_stem="",
        valve_length="",
        valve_od="",
        center_to_edge="",
        diff_pressure="0,35",
    )
    assert kvs_for_sku(series, "8100-bv215a") == "1,6"
    assert kvs_for_sku(series, "8100-BV215E") == "10,1"
    assert kvs_for_sku(series, "8100-bv220a") is None


def test_diff_pressure_mpa_defaults_only_when_blank() -> None:
    """Default 0,35 applies only for missing/blank; unit strip keeps numeric body."""
    assert _diff_pressure_mpa(None) == "0,35"
    assert _diff_pressure_mpa("") == "0,35"
    assert _diff_pressure_mpa("   ") == "0,35"
    assert _diff_pressure_mpa("0,35 МПа") == "0,35"
    assert _diff_pressure_mpa("0,5 МПа") == "0,5"


def test_format_compatible_actuators_bracket_only_with_fu() -> None:
    """Drives and bracket are separate; BR-ML only when DA…FU is listed."""
    drives = format_compatible_actuators(("DA5FU24", "DA6MU24"))
    assert "DA5FU24" in drives
    assert "BR-M" not in drives
    assert format_bracket(("DA5FU24", "DA6MU24")) == ("BR-M / BR-ML (для DA…FU)")
    assert format_bracket(("DA6MU24", "DA8MQU24")) == "BR-M"


def test_load_ball_valve_series_from_csv() -> None:
    """Store CSV yields all 12 BV series with DN / Kvs / drives / photos."""
    series_list = load_ball_valve_series()
    by_code = {s.code: s for s in series_list}
    assert set(by_code) >= {
        "BV215",
        "BV220",
        "BV225",
        "BV250",
        "BV315",
        "BV350",
    }

    bv220 = by_code["BV220"]
    assert bv220.dn == "20"
    assert bv220.ways == "2-ходовый"
    assert "G 3/4" in bv220.thread
    assert bv220.kvs_by_edition["a"] == "1,6"
    assert "DA6MU24" in bv220.drive_series
    assert "DA5FU24" in bv220.drive_series
    assert "DA8MQU24" in bv220.drive_series
    assert bv220.bracket == "BR-M / BR-ML (для DA…FU)"
    assert len(bv220.gallery_urls) == 3

    bv315 = by_code["BV315"]
    assert bv315.ways == "3-ходовый"
    assert bv315.center_to_edge == "30"
    assert bv315.voltage_label == "230 В"
    assert "DA5FU230" in bv315.drive_series
    assert "DA5FU30" not in bv315.drive_series


def test_label_to_slug_valve_fields() -> None:
    """Valve ТТХ labels resolve to canonical slugs."""
    assert label_to_slug("Рабочая среда") == "medium"
    assert label_to_slug("Рабочая температура среды") == "media-temp"
    assert label_to_slug("Резьба внутренняя") == "thread"
    assert label_to_slug("Максимальный рабочий перепад давления") == ("diff-pressure")
    assert label_to_slug("Длина от центра до края крана") == "center-to-edge"


@pytest.mark.django_db
def test_apply_bv220_enrichment_cards_and_gallery() -> None:
    """BV220 follows the same card template as BV215."""
    series = next(s for s in load_ball_valve_series() if s.code == "BV220")
    cat = Category.objects.create(name="Краны test", slug="krany-bv220-test")
    product = Product.objects.create(
        category=cat,
        name="old",
        slug=product_slug_for_series("BV220"),
        description="old",
        specs_text="legacy",
    )
    for letter in ("a", "b"):
        SKU.objects.create(
            product=product,
            name="old name",
            slug=f"bv220-test-{letter}",
            sku_code=f"8100-bv220{letter}",
            description="old",
            specs_text="x",
            is_published=True,
        )

    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(200, 200, 200)).save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    with patch(
        "catalog.management.commands.import_tilda_images._download",
        return_value=jpeg_bytes,
    ):
        stats = apply_series_enrichment(series, import_images=True)

    assert stats["products"] == 1
    assert stats["images_failed"] == 0
    assert stats["images_created"] >= 3

    sku_a = SKU.objects.get(sku_code="8100-bv220a")
    assert "Kvs 1,6" in sku_a.description
    by_slug = {
        av.attribute.slug: av.value
        for av in AttributeValue.objects.filter(sku=sku_a).select_related(
            "attribute",
        )
    }
    assert by_slug["dn"] == "20"
    assert by_slug["ways"] == "2-ходовый"
    assert by_slug["kvs"] == "1,6"
    assert "3/4" in by_slug["thread"]
    assert by_slug["valve-length"] == "68"
    assert "DA6MU24" in by_slug["compatible-actuators"]
    assert "DA5FU24" in by_slug["compatible-actuators"]
    assert "BR-ML" not in by_slug["compatible-actuators"]
    assert by_slug["bracket"] == "BR-M / BR-ML (для DA…FU)"
    assert ProductImage.objects.filter(sku=sku_a).count() == 3

    from catalog.serializers import SKUDetailSerializer

    data = SKUDetailSerializer(sku_a).data
    hl_keys = {h["key"] for h in data["highlights"]}
    assert {"dn", "ways", "kvs", "compatible-actuators", "bracket"} <= hl_keys


def test_drive_families_from_mods_first_segment() -> None:
    """Marker in the first ``|`` segment yields unique drive bases."""
    mods = "Выбор привода:Не выбран;da6mu24-d;da6mu24-ds;da8mqu24-a|Выбор кронштейна:Не выбран;BR-M"
    assert _drive_families_from_mods(mods) == ["DA6MU24", "DA8MQU24"]


def test_drive_families_from_mods_marker_after_pipe() -> None:
    """Marker after ``|`` must not IndexError; parse that segment."""
    mods = "Выбор кронштейна:Не выбран;BR-M|Выбор привода:Не выбран;da5fu24-d;da5fu24-ds"
    assert _drive_families_from_mods(mods) == ["DA5FU24"]


def test_drive_families_from_mods_missing_marker() -> None:
    assert _drive_families_from_mods("Выбор кронштейна:BR-M") == []


def test_apply_bv215_enrichment_delegates_and_strips_series_key() -> None:
    """BV215 wrapper drops ``series`` counter from the multi-series stats."""
    from catalog.etl.series_copy_bv215 import apply_bv215_enrichment

    fake = {
        "products": 1,
        "skus": 2,
        "attributes": 10,
        "images_created": 3,
        "images_failed": 0,
        "series": 1,
    }
    with patch(
        "catalog.etl.series_copy_bv215.apply_all_ball_valve_enrichment",
        return_value=fake,
    ) as mocked:
        out = apply_bv215_enrichment(import_images=False)
    mocked.assert_called_once_with(
        import_images=False,
        series_codes=("BV215",),
    )
    assert out == {
        "products": 1,
        "skus": 2,
        "attributes": 10,
        "images_created": 3,
        "images_failed": 0,
    }
    assert "series" not in out


def test_kvs_for_sku_code_returns_none_when_series_missing() -> None:
    """If BV215 is absent from loaded series, Kvs lookup yields None."""
    with patch(
        "catalog.etl.series_copy_bv215.load_ball_valve_series",
        return_value=[],
    ):
        assert kvs_for_sku_code("8100-bv215a") is None
