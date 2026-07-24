"""Tests for BV* ball-valve series copy (CSV → cards)."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

from catalog.etl.label_to_slug import label_to_slug
from catalog.etl.series_copy_ball_valves import (
    DEFAULT_STORE_CSV,
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

requires_store_csv = pytest.mark.skipif(
    not DEFAULT_STORE_CSV.is_file(),
    reason="Sibling hoocon store CSV not available in CI",
)


def test_product_slug_for_series_is_8100_bv() -> None:
    """Brass DN cards use ``8100-bv215`` (not ``sharovoy-kran-bv215``)."""
    assert product_slug_for_series("BV215") == "8100-bv215"
    assert product_slug_for_series("bv220") == "8100-bv220"


@requires_store_csv
def test_kvs_for_sku_code_editions() -> None:
    """Edition letters a–e map to Tilda Kvs values for BV215."""
    assert kvs_for_sku_code("8100-bv215a") == "1,6"
    assert kvs_for_sku_code("8100-BV215E") == "10,1"
    assert kvs_for_sku_code("8100-bv220a") is None


def test_kvs_for_sku_matches_full_series_number() -> None:
    """BV prefix strip compares full 3-digit series (BV215 → «215», not «15»)."""
    series = BallValveSeries(
        code="BV215",
        product_slug="8100-bv215",
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


def test_kvs_for_flanged_kit_body_kvs() -> None:
    """Flanged kit bodies keep a single Kvs; editions are electrical, not a–e."""
    from catalog.etl.series_copy_ball_valves import flanged_kit_series

    kit = next(k for k in flanged_kit_series() if k.code == "H8103-BV2100")
    assert kit.kvs == "160"
    assert kit.run_time == "< 150 с"
    assert kit.material == "ВЧШГ"
    assert kit.product_slug == "h8103"
    assert kit.sku_display_name.startswith("H8103-BV2100")


def test_flanged_kit_edition_matrix_has_80_unique_codes() -> None:
    """H8103/H8104 alone: 2 × 5 bodies × 8 editions = 80 SKU codes."""
    from catalog.etl.series_copy_ball_valves import (
        flanged_kit_edition_sku_codes,
        flanged_kit_series,
    )

    kits = [k for k in flanged_kit_series() if k.kit in {"H8103", "H8104"}]
    assert len(kits) == 10
    codes = [c for kit in kits for c in flanged_kit_edition_sku_codes(kit)]
    assert len(codes) == 80
    assert len(set(codes)) == 80
    assert "H8103-BV265-24A" in codes
    assert "H8104-BV2150-230DS" in codes
    assert {k.product_slug for k in kits} == {"h8103", "h8104"}


def test_h81_full_kit_matrix_counts() -> None:
    """H8101…H8122: 174 body rows × 8 = 1392 SKU; 10 family Product slugs."""
    from catalog.etl.h81_kits import (
        all_h81_kit_series,
        h81_family_prefixes,
        h81_kit_edition_sku_codes,
    )

    cards = all_h81_kit_series()
    assert len(cards) == 174
    codes = [c for kit in cards for c in h81_kit_edition_sku_codes(kit)]
    assert len(codes) == 1392
    assert len(set(codes)) == 1392
    slugs = {kit.product_slug for kit in cards}
    assert slugs == {p.casefold() for p in h81_family_prefixes()}
    assert len(slugs) == 10
    assert "H8101-BV215A-24AS" in codes
    assert "H8105-BV350B-230D" in codes
    assert "H8107-BV265-24A" in codes
    assert "H8121-BV2150-230DS" in codes
    assert not any(c.startswith("H8205") for c in codes)


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


@requires_store_csv
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
@requires_store_csv
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


@pytest.mark.django_db
def test_ensure_and_enrich_brass_h8101_bv215a() -> None:
    """H8101-BV215A seeds 8 electrical SKUs on family Product ``h8101``."""
    from catalog.ball_valve_kit import build_ball_valve_kit_options
    from catalog.etl.series_copy_ball_valves import (
        apply_flanged_kit_enrichment,
        flanged_kit_series,
    )

    Category.objects.create(name="Комплекты", slug="komplekty")
    kit = next(k for k in flanged_kit_series() if k.code == "H8101-BV215A")
    stats = apply_flanged_kit_enrichment(kit, import_images=False, attach_pdf=False)
    assert stats["products"] == 1
    assert stats["skus"] == 8
    product = Product.objects.get(slug="h8101")
    assert product.skus.count() == 8
    sku = SKU.objects.get(sku_code="H8101-BV215A-24AS")
    assert sku.product_id == product.pk
    assert sku.slug.startswith("h8101-")
    by_slug = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")
    }
    assert by_slug["dn"] == "15"
    assert by_slug["kvs"] == "1,6"
    assert by_slug["material"] == "Латунь"
    assert by_slug["power-consumption"] == ("В рабочем режиме: 3 Вт / В режиме ожидания: 1 Вт")
    assert by_slug["aux-switch"] == "SPDT-2"
    assert "thread" in by_slug
    assert "24" in by_slug["voltage"]
    assert "двумя вспомогательными переключателями" in sku.description
    assert build_ball_valve_kit_options(sku) is None

    plain = SKU.objects.get(sku_code="H8101-BV215A-24A")
    plain_slugs = {av.attribute.slug for av in AttributeValue.objects.filter(sku=plain).select_related("attribute")}
    assert "aux-switch" not in plain_slugs
    assert "без вспомогательных переключателей" in plain.description
    ds = SKU.objects.get(sku_code="H8101-BV215A-24DS")
    ds_aux = AttributeValue.objects.get(sku=ds, attribute__slug="aux-switch").value
    assert ds_aux == "SPDT-2"

    kit_b = next(k for k in flanged_kit_series() if k.code == "H8101-BV215B")
    apply_flanged_kit_enrichment(kit_b, import_images=False, attach_pdf=False)
    assert Product.objects.filter(slug="h8101").count() == 1
    assert SKU.objects.filter(product__slug="h8101").count() == 16


@pytest.mark.django_db
def test_ensure_and_enrich_flanged_h8103_bv265() -> None:
    """H8103-BV265 seeds 8 electrical SKUs with voltage/control, no RFQ drives."""
    from catalog.ball_valve_kit import build_ball_valve_kit_options
    from catalog.etl.series_copy_ball_valves import (
        apply_flanged_kit_enrichment,
        flanged_kit_series,
    )

    Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    kit = next(k for k in flanged_kit_series() if k.code == "H8103-BV265")
    stats = apply_flanged_kit_enrichment(kit, import_images=False, attach_pdf=False)
    assert stats["products"] == 1
    assert stats["skus"] == 8
    sku = SKU.objects.get(sku_code="H8103-BV265-24AS")
    by_slug = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")
    }
    assert by_slug["dn"] == "65"
    assert by_slug["kvs"] == "63"
    assert by_slug["material"] == "ВЧШГ"
    assert "фланц" in by_slug["connection"].casefold()
    assert "24" in by_slug["voltage"]
    assert "compatible-actuators" not in by_slug
    assert build_ball_valve_kit_options(sku) is None


@pytest.mark.django_db
def test_retire_legacy_8100_flanged_redirects_to_h8103() -> None:
    """Legacy 8100-bv265 is unpublished and 301'd to H8103-BV265-24A."""
    from catalog.etl.series_copy_ball_valves import (
        apply_flanged_kit_enrichment,
        flanged_kit_series,
        retire_legacy_flanged_body_skus,
    )
    from redirects.models import Redirect

    cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    product = Product.objects.create(
        name="BV265",
        slug="sharovoy-kran-bv265",
        category=cat,
    )
    legacy = SKU.objects.create(
        product=product,
        name="BV265",
        slug="sharovoy-kran-bv265-8100-bv265",
        sku_code="8100-bv265",
        is_published=True,
    )
    kit = next(k for k in flanged_kit_series() if k.code == "H8103-BV265")
    apply_flanged_kit_enrichment(kit, import_images=False, attach_pdf=False)
    retired = retire_legacy_flanged_body_skus()
    legacy.refresh_from_db()
    assert legacy.is_published is False
    assert retired["skus_unpublished"] >= 1
    target = SKU.objects.get(sku_code="H8103-BV265-24A")
    assert Redirect.objects.filter(
        from_path__contains=legacy.slug,
        to_path__contains=target.slug,
        is_active=True,
    ).exists()


@pytest.mark.django_db
@requires_store_csv
def test_merge_brass_bv_onto_8100_dn_products() -> None:
    """Legacy ``sharovoy-kran-bv215`` SKUs move to ``8100-bv215`` + 301."""
    from catalog.etl.series_copy_ball_valves import merge_brass_bv_onto_dn_products
    from redirects.models import Redirect

    cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    legacy = Product.objects.create(
        name="BV215 old",
        slug="sharovoy-kran-bv215",
        category=cat,
    )
    sku = SKU.objects.create(
        product=legacy,
        name="8100-bv215a",
        slug="sharovoy-kran-bv215-8100-bv215a",
        sku_code="8100-bv215a",
        is_published=True,
    )
    stats = merge_brass_bv_onto_dn_products(series_codes=("BV215",))
    sku.refresh_from_db()
    assert sku.product.slug == "8100-bv215"
    assert sku.slug == "8100-bv215-8100-bv215a"
    assert stats["skus_moved"] >= 1
    assert stats["slugs_renamed"] >= 1
    assert not Product.objects.filter(slug="sharovoy-kran-bv215").exists()
    assert Redirect.objects.filter(
        from_path="/catalog/sharovye-krany/sharovoy-kran-bv215-8100-bv215a",
        to_path="/catalog/sharovye-krany/8100-bv215-8100-bv215a",
        is_active=True,
    ).exists()
