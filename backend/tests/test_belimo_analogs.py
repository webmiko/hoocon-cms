"""Belimo analog extraction from card copy and spec-based inference."""

from __future__ import annotations

import pytest
from django.urls import reverse

from catalog.etl.belimo_analogs import (
    analogs_plain_text_for_sku,
    belimo_code_is_modulating,
    belimo_code_is_thermal,
    belimo_code_matches_control,
    belimo_codes_for_sku,
    extract_belimo_codes_from_text,
    infer_belimo_codes,
    normalize_belimo_code,
    primary_belimo_code_for_sku,
    sku_code_is_thermal,
)
from catalog.models import (
    SKU,
    Attribute,
    AttributeValue,
    Category,
    Product,
)


def test_normalize_belimo_code_dashes() -> None:
    """Unicode dashes collapse to ASCII hyphen."""
    assert normalize_belimo_code("nf24a−s") == "NF24A-S"
    assert normalize_belimo_code(" LM24A-S. ") == "LM24A-S"


def test_analogs_plain_text_for_sku_tolerates_missing_product() -> None:
    """product_id set but product missing must not raise on analogs fallback."""
    from unittest.mock import MagicMock

    sku = MagicMock()
    sku.sku_code = "HVD24-5"
    sku.analogs_text = ""
    sku.product_id = 99
    sku.product = None
    assert analogs_plain_text_for_sku(sku) == ""

    sku.analogs_text = "– Belimo LM24A\n"
    assert "LM24A" in extract_belimo_codes_from_text(analogs_plain_text_for_sku(sku))[0]


def test_analogs_plain_text_empty_sku_does_not_inherit_product() -> None:
    """Empty SKU analogs_text must not re-fetch / inherit product analogs."""
    from unittest.mock import MagicMock, patch

    sku = MagicMock()
    sku.sku_code = "HVD24-5"
    sku.analogs_text = ""
    with patch(
        "catalog.sku_access.sku_product_field",
        return_value="– Belimo LM24A\n",
    ) as product_field:
        assert analogs_plain_text_for_sku(sku) == ""
        product_field.assert_not_called()


def test_analogs_plain_text_none_sku_inherits_product() -> None:
    """Unset (None) SKU analogs_text falls back to product section text."""
    from unittest.mock import MagicMock, patch

    sku = MagicMock()
    sku.sku_code = "HVD24-5"
    sku.analogs_text = None
    with patch(
        "catalog.sku_access.sku_product_field",
        return_value="– Belimo LF24-S\n",
    ):
        assert "LF24-S" in extract_belimo_codes_from_text(
            analogs_plain_text_for_sku(sku),
        )


def test_extract_belimo_codes_from_analogs_block() -> None:
    """Lines like «– Belimo LF24-S» yield article codes."""
    text = """
    Аналоги для Hoocon DA5FU24-DS:
    – Nanotek LF 24
    – Belimo LF24-S
    – Belimo LF24-RS
    – Sputnik AS24-05-S
    """
    assert extract_belimo_codes_from_text(text) == ["LF24-S", "LF24-RS"]


def test_extract_filters_by_sku_voltage() -> None:
    """230 В Belimo codes are dropped for a 24 В edition."""
    text = """
    – Belimo NF24A
    – Belimo NF10-230
    – Belimo FSR-230-3N
    """
    assert extract_belimo_codes_from_text(text, voltage="24") == ["NF24A"]
    assert extract_belimo_codes_from_text(text, voltage="230") == [
        "NF10-230",
        "FSR-230-3N",
    ]


@pytest.mark.django_db
def test_belimo_codes_filters_aux_suffix_from_shared_block() -> None:
    """Shared HVD analogs block keeps -S only for S-editions."""
    cat = Category.objects.create(name="Air", slug="air-aux-analog")
    product = Product.objects.create(name="HVD20", slug="hvd20-aux", category=cat)
    text = """
    аналоги HVD24-20
    – Belimo NM24A-SR-20
    аналоги HVD24S-20
    – Belimo NM24A-SR-20-S
    """
    bare = SKU.objects.create(
        product=product,
        name="HVD24-20",
        slug="hvd24-20-aux",
        sku_code="HVD24-20",
        is_published=True,
        analogs_text=text,
    )
    with_s = SKU.objects.create(
        product=product,
        name="HVD24S-20",
        slug="hvd24s-20-aux",
        sku_code="HVD24S-20",
        is_published=True,
        analogs_text=text,
    )
    assert belimo_codes_for_sku(bare) == ["NM24A-SR-20"]
    assert belimo_codes_for_sku(with_s) == ["NM24A-SR-20-S"]


@pytest.mark.django_db
def test_belimo_codes_strips_lone_s_for_non_aux_damu_d() -> None:
    """Shared D/DS card with only LM24A-S → D gets LM24A, DS keeps -S."""
    cat = Category.objects.create(name="Air", slug="air-damu-aux-analog")
    product = Product.objects.create(
        name="DA4MU",
        slug="da4mu-aux-analog",
        category=cat,
        analogs_text="""
Аналоги для DA4MU24-D/DS (24 В, 4Нм):
– Belimo LM24A-S (без возвратной пружины)
""",
    )
    bare = SKU.objects.create(
        product=product,
        name="DA4MU24-D",
        slug="da4mu24-d-aux",
        sku_code="DA4MU24-D",
        is_published=True,
        analog_belimo_code="LM24A-S",
    )
    with_s = SKU.objects.create(
        product=product,
        name="DA4MU24-DS",
        slug="da4mu24-ds-aux",
        sku_code="DA4MU24-DS",
        is_published=True,
        analog_belimo_code="LM24A-S",
    )
    assert belimo_codes_for_sku(bare) == ["LM24A"]
    assert belimo_codes_for_sku(with_s) == ["LM24A-S"]
    assert primary_belimo_code_for_sku(bare) == "LM24A"
    assert primary_belimo_code_for_sku(with_s) == "LM24A-S"


def test_infer_air_no_spring_by_moment_voltage_aux_control() -> None:
    """HVD-class: LM/NM/GM by moment + voltage + aux + control."""
    assert infer_belimo_codes(
        purpose="air_no_spring",
        moment_nm=5.0,
        voltage="24",
        control="on_off",
        aux_spdt=0,
    ) == ["LM24A"]
    assert infer_belimo_codes(
        purpose="air_no_spring",
        moment_nm=5.0,
        voltage="24",
        control="on_off",
        aux_spdt=2,
    ) == ["LM24A-S"]
    assert infer_belimo_codes(
        purpose="air_no_spring",
        moment_nm=10.0,
        voltage="230",
        control="modulating",
        aux_spdt=0,
    ) == ["NM230A-SR"]
    assert infer_belimo_codes(
        purpose="air_no_spring",
        moment_nm=40.0,
        voltage="24",
        control="on_off",
        aux_spdt=2,
    ) == ["GM24A-S"]


def test_infer_fire_spring_family() -> None:
    """Fire/smoke spring-return → Belimo BFL/BLF/BFN by torque band."""
    assert infer_belimo_codes(
        purpose="fire_spring",
        moment_nm=3.0,
        voltage="24",
        control="on_off",
        aux_spdt=2,
        thermal=False,
    ) == ["BFL24"]
    assert infer_belimo_codes(
        purpose="fire_spring",
        moment_nm=5.0,
        voltage="24",
        control="on_off",
        aux_spdt=2,
        thermal=False,
    ) == ["BLF24"]
    assert infer_belimo_codes(
        purpose="fire_spring",
        moment_nm=5.0,
        voltage="230",
        control="on_off",
        aux_spdt=2,
        thermal=True,
    ) == ["BLF230-T"]
    assert infer_belimo_codes(
        purpose="fire_spring",
        moment_nm=10.0,
        voltage="230",
        control="on_off",
        aux_spdt=0,
        thermal=True,
    ) == ["BFN230-T"]


def test_detect_purpose_hvd_is_fire_spring() -> None:
    """HVD-…F must not inherit category smoke→CM (SA..MU lives in same category)."""
    from catalog.etl.belimo_analogs import detect_purpose

    slug = "elektroprivody-dlya-klapanov-dymoudaleniya"
    assert detect_purpose(category_slug=slug, sku_code="HVD24S-3F") == "fire_spring"
    assert detect_purpose(category_slug=slug, sku_code="HVD230ST-5F") == "fire_spring"
    assert detect_purpose(category_slug=slug, sku_code="SA10MU24-DS") == "smoke"
    # Bare / Q HVD are air (non-spring), not fire BFL/BLF.
    assert detect_purpose(category_slug=slug, sku_code="HVD24-40") == "air_no_spring"
    assert detect_purpose(category_slug=slug, sku_code="HVD24S-20") == "air_no_spring"
    assert detect_purpose(category_slug=slug, sku_code="HVD24-10Q") == "fast"
    assert detect_purpose(category_slug=slug, sku_code="HVD230S-40QX") == "fast"


def test_infer_fast_actuator() -> None:
    """Accelerated DA8MQU / HVA → NMQ / BM families."""
    assert infer_belimo_codes(
        purpose="fast",
        moment_nm=8.0,
        voltage="24",
        control="modulating",
        aux_spdt=2,
    ) == ["NMQ24A-SR-S"]
    assert infer_belimo_codes(
        purpose="fast",
        moment_nm=5.0,
        voltage="24",
        control="modulating",
        aux_spdt=0,
    ) == ["BM24-5-05"]


@pytest.mark.django_db
def test_belimo_codes_for_sku_prefers_card_text() -> None:
    """SKU with analogs_text uses Belimo lines; field is secondary."""
    cat = Category.objects.create(name="Air", slug="air-analog-test")
    product = Product.objects.create(name="DA5", slug="da5-analog-test", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA5FU24-DS",
        slug="da5fu24-ds-analog-test",
        sku_code="da5fu24-ds",
        is_published=True,
        analog_belimo_code="WRONG24",
        analogs_text="Аналог DA5FU24-DS:\n– Belimo LF24-S\n– Belimo LF24-RS\n",
    )
    assert belimo_codes_for_sku(sku) == ["LF24-S", "LF24-RS"]


def test_belimo_code_control_sr_token() -> None:
    """Open/close vs ``-SR``; spring ``LF24-RS`` stays ambiguous (kept)."""
    assert belimo_code_is_modulating("LM24A-SR") is True
    assert belimo_code_is_modulating("LM24A-SR-S") is True
    assert belimo_code_is_modulating("NM24A-SR-20") is True
    assert belimo_code_is_modulating("LM24A-S") is False
    assert belimo_code_is_modulating("CM230-L/R") is False
    assert belimo_code_matches_control("CM230-L/R", "on_off") is True
    assert belimo_code_matches_control("CM230-L/R", "modulating") is False
    assert belimo_code_matches_control("LM230A-S", "modulating") is False
    assert belimo_code_matches_control("LM230A-SR-S", "modulating") is True
    assert belimo_code_matches_control("LM230A-SR-S", "on_off") is False
    assert belimo_code_matches_control("LF24-RS", "modulating") is True
    assert belimo_code_matches_control("LF24-RS", "on_off") is True
    assert belimo_code_matches_control("LF24-S", "modulating") is True


@pytest.mark.django_db
def test_shared_ds_as_block_splits_belimo_by_control() -> None:
    """Combined ``…-DS/…-AS`` card text must not pin one Belimo on both sides."""
    cat = Category.objects.create(
        name="Air no spring",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(name="DA2MU", slug="da2mu-shared-analog", category=cat)
    text = """
Список аналогов для привода серии DA..MU 2 Нм

Для Hoocon DA2MU230-DS/DA2MU230-AS (230В):

– Belimo CM230-L/R

Основные характеристики аналогов
Управление: 2-/3-позиционное
""".strip()
    moment = Attribute.objects.create(name="Крутящий момент", slug="moment")
    voltage = Attribute.objects.create(name="Напряжение", slug="voltage")
    control = Attribute.objects.create(name="Управление", slug="control")
    aux = Attribute.objects.create(name="Вспомогательный переключатель", slug="aux-switch")

    ds = SKU.objects.create(
        product=product,
        name="DA2MU230-DS",
        slug="da2mu230-ds-shared",
        sku_code="DA2MU230-DS",
        is_published=True,
        analog_belimo_code="CM230-L/R",
        analogs_text=text,
    )
    AttributeValue.objects.create(sku=ds, attribute=moment, value="2 Нм")
    AttributeValue.objects.create(sku=ds, attribute=voltage, value="AC 230 В")
    AttributeValue.objects.create(sku=ds, attribute=control, value="Открыто/закрыто")
    AttributeValue.objects.create(sku=ds, attribute=aux, value="SPDT-1")

    as_sku = SKU.objects.create(
        product=product,
        name="DA2MU230-AS",
        slug="da2mu230-as-shared",
        sku_code="DA2MU230-AS",
        is_published=True,
        analog_belimo_code="CM230-L/R",
        analogs_text=text,
    )
    AttributeValue.objects.create(sku=as_sku, attribute=moment, value="2 Нм")
    AttributeValue.objects.create(sku=as_sku, attribute=voltage, value="AC 230 В")
    AttributeValue.objects.create(sku=as_sku, attribute=control, value="Пропорциональное")
    AttributeValue.objects.create(sku=as_sku, attribute=aux, value="SPDT-1")

    assert belimo_codes_for_sku(ds) == ["CM230-L/R"]
    assert belimo_codes_for_sku(as_sku) == ["LM230A-SR-S"]
    assert primary_belimo_code_for_sku(as_sku) == "LM230A-SR-S"

    as_text = analogs_plain_text_for_sku(as_sku)
    assert "CM230-L/R" not in as_text
    assert "DA2MU230-AS" in as_text
    ds_text = analogs_plain_text_for_sku(ds)
    assert "CM230-L/R" in ds_text


@pytest.mark.django_db
def test_damu_2nm_split_analogs_by_control() -> None:
    """Split DA2MU card: on/off keeps CM*, modulating keeps LM*-SR only."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "catalog" / "etl" / "data" / "damu_2nm_analogs.txt").read_text(
        encoding="utf-8"
    )
    cat = Category.objects.create(
        name="Air no spring",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(
        name="DA2MU",
        slug="da2mu-2nm-split",
        category=cat,
        analogs_text=text,
    )
    ds = SKU.objects.create(
        product=product,
        name="DA2MU230-DS",
        slug="da2mu230-ds-split",
        sku_code="DA2MU230-DS",
        is_published=True,
        analogs_text=text,
    )
    as_sku = SKU.objects.create(
        product=product,
        name="DA2MU230-AS",
        slug="da2mu230-as-split",
        sku_code="DA2MU230-AS",
        is_published=True,
        analogs_text=text,
    )
    ds_text = analogs_plain_text_for_sku(ds)
    as_text = analogs_plain_text_for_sku(as_sku)
    assert "CM230-L/R" in ds_text
    assert "LM230A-SR" not in ds_text
    assert "Dastech" in ds_text
    assert "CM230-L/R" not in as_text
    assert extract_belimo_codes_from_text(as_text) == ["LM230A-SR-S"]
    assert "Dastech" not in as_text
    assert belimo_codes_for_sku(ds) == ["CM230-L/R"]
    assert belimo_codes_for_sku(as_sku) == ["LM230A-SR-S"]
    assert primary_belimo_code_for_sku(as_sku) == "LM230A-SR-S"


@pytest.mark.django_db
def test_belimo_codes_for_sku_infers_when_text_empty() -> None:
    """Missing analogs_text → infer from EAV + category."""
    cat = Category.objects.create(
        name="Air no spring",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(name="DA5MU", slug="da5mu-analog-test", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA5MU24-D",
        slug="da5mu24-d-analog-test",
        sku_code="DA5MU24-D",
        is_published=True,
    )
    moment = Attribute.objects.create(name="Крутящий момент", slug="moment")
    voltage = Attribute.objects.create(name="Напряжение (В)", slug="voltage")
    control = Attribute.objects.create(name="Управление", slug="control")
    aux = Attribute.objects.create(name="Вспомогательные переключатели", slug="aux-switch")
    AttributeValue.objects.create(sku=sku, attribute=moment, value="5 Нм")
    AttributeValue.objects.create(sku=sku, attribute=voltage, value="AC/DC 24 В, 50/60 Гц")
    AttributeValue.objects.create(sku=sku, attribute=control, value="Открыто/закрыто")
    AttributeValue.objects.create(sku=sku, attribute=aux, value="Нет")
    assert belimo_codes_for_sku(sku) == ["LM24A"]


@pytest.mark.django_db
def test_analog_facet_from_card_text(client) -> None:
    """«Аналоги» facet lists Belimo codes parsed from analogs_text."""
    cat = Category.objects.create(name="Spring", slug="spring-analog-facet")
    product = Product.objects.create(name="DA5FU", slug="da5fu-facet", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA5FU24-DS",
        slug="da5fu24-ds-facet",
        sku_code="da5fu24-ds",
        is_published=True,
        analogs_text="– Belimo LF24-S\n– Belimo LF24-RS\n",
    )
    facets = client.get(reverse("catalog-facet-list"))
    assert facets.status_code == 200
    by_key = {row["key"]: row for row in facets.data["results"]}
    assert "analog" in by_key
    codes = {v["value"] for v in by_key["analog"]["values"]}
    assert "LF24-S" in codes
    assert "LF24-RS" in codes

    filtered = client.get(reverse("catalog-sku-list"), {"analog": "LF24-S"})
    assert filtered.status_code == 200
    assert {row["slug"] for row in filtered.data["results"]} == {sku.slug}


@pytest.mark.django_db
def test_sku_attr_map_keeps_first_slug_value() -> None:
    """Duplicate slugs in the attr list keep the first value (first-wins)."""
    from types import SimpleNamespace

    from catalog.etl.belimo_analogs import _sku_attr_map

    cat = Category.objects.create(name="Air", slug="air-attr-map")
    product = Product.objects.create(name="P", slug="p-attr-map", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SKU",
        slug="sku-attr-map",
        sku_code="SKU-ATTR-MAP",
        is_published=True,
    )

    def av(slug: str, value: str, name: str = "") -> SimpleNamespace:
        return SimpleNamespace(
            attribute=SimpleNamespace(slug=slug, name=name),
            value=value,
        )

    # Prefetch may theoretically list the same slug twice; do not last-wins.
    sku._prefetched_attribute_values = [  # type: ignore[attr-defined]
        av("moment", "5 Нм", "Момент"),
        av("moment", "10 Нм", "Момент"),
        av("attr-dup", "first"),
        av("attr-dup", "second"),
    ]
    attrs = _sku_attr_map(sku)
    assert attrs["moment"] == "5 Нм"
    assert attrs["attr-dup"] == "first"


def test_sku_code_is_thermal_suffix_only() -> None:
    """Thermal detection requires DST / -T / HVD…ST-…F, not a mid-string match."""
    assert sku_code_is_thermal("SA5FU24-DST") is True
    assert sku_code_is_thermal("sa5fu24-dst") is True
    assert sku_code_is_thermal("BF24-T") is True
    assert sku_code_is_thermal("SA5FU24DST") is True
    assert sku_code_is_thermal("HVD24ST-3F") is True
    assert sku_code_is_thermal("HVD230ST-5F") is True
    assert sku_code_is_thermal("HVD24S-3F") is False
    assert sku_code_is_thermal("DSTXXX") is False
    assert sku_code_is_thermal("XDSTX") is False
    assert sku_code_is_thermal("SA5FU24") is False
    assert sku_code_is_thermal("") is False
    assert sku_code_is_thermal(None) is False


def test_belimo_code_is_thermal_suffix_only() -> None:
    """Thermal Belimo: ``-T`` / ``FST`` / smoke ``…ST`` family codes."""
    assert belimo_code_is_thermal("BF24-T") is True
    assert belimo_code_is_thermal("bf24-t") is True
    assert belimo_code_is_thermal("BF24-FST") is True
    assert belimo_code_is_thermal("FST-230-3N") is True
    assert belimo_code_is_thermal("FST-24-3N") is True
    assert belimo_code_is_thermal("BEE24ST") is True
    assert belimo_code_is_thermal("BEE230ST") is True
    assert belimo_code_is_thermal("X-T-Y") is False
    assert belimo_code_is_thermal("BF24-S") is False
    assert belimo_code_is_thermal("BEE24") is False
    assert belimo_code_is_thermal("XFSTY") is False
    assert belimo_code_is_thermal("FSR-230-3N") is False
    assert belimo_code_is_thermal("") is False
    assert belimo_code_is_thermal(None) is False


@pytest.mark.django_db
def test_primary_belimo_ignores_midstring_dst_as_thermal() -> None:
    """Codes with mid-string DST must use the first Belimo code (non-thermal path)."""
    cat = Category.objects.create(name="Air", slug="air-mid-dst")
    product = Product.objects.create(name="SA", slug="sa-mid-dst", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DSTXXX",
        slug="dstxxx-mid",
        sku_code="DSTXXX",
        is_published=True,
        analogs_text="– Belimo LM24A\n– Belimo BF24-T\n",
    )
    assert primary_belimo_code_for_sku(sku) == "LM24A"


@pytest.mark.django_db
def test_primary_belimo_skips_midstring_dash_t_belimo_code() -> None:
    """Thermal SKU must not treat mid-string -T Belimo tokens as thermal."""
    cat = Category.objects.create(name="Fire", slug="fire-mid-t")
    product = Product.objects.create(name="SA", slug="sa-mid-t", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA5FU24-DST",
        slug="sa5fu24-dst-mid-t",
        sku_code="SA5FU24-DST",
        is_published=True,
        analogs_text="– Belimo LM24A-T-S\n– Belimo BF24-S\n",
    )
    assert belimo_codes_for_sku(sku) == ["LM24A-T-S", "BF24-S"]
    assert belimo_code_is_thermal("LM24A-T-S") is False
    assert primary_belimo_code_for_sku(sku) is None


@pytest.mark.django_db
def test_primary_belimo_prefers_thermal_code_for_dst_sku() -> None:
    """Thermal Hoocon editions pick FST/-T Belimo codes when present."""
    cat = Category.objects.create(name="Fire", slug="fire-thermal-pick")
    product = Product.objects.create(name="SA", slug="sa-thermal-pick", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA5FU24-DST",
        slug="sa5fu24-dst-pick",
        sku_code="SA5FU24-DST",
        is_published=True,
        analogs_text="– Belimo BF24-S\n– Belimo BF24-T\n",
    )
    assert primary_belimo_code_for_sku(sku) == "BF24-T"


@pytest.mark.django_db
def test_primary_belimo_skips_non_thermal_fallback_for_dst_sku() -> None:
    """Thermal SKU must not persist a non-thermal Belimo code as primary.

    ``-dst`` editions have aux switches, so BASE / BASE-S pairs keep only ``-S``;
    without a thermal Belimo article (``-T`` / ``FST``) primary stays empty.
    """
    cat = Category.objects.create(name="Fire", slug="fire-thermal-none")
    product = Product.objects.create(name="SA", slug="sa-thermal-none", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA5FU24-DST",
        slug="sa5fu24-dst-none",
        sku_code="SA5FU24-DST",
        is_published=True,
        analogs_text="– Belimo BF24-S\n– Belimo BF24\n",
    )
    assert belimo_codes_for_sku(sku) == ["BF24-S"]
    assert primary_belimo_code_for_sku(sku) is None
