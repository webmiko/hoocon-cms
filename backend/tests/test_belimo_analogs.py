"""Belimo analog extraction from card copy and spec-based inference."""

from __future__ import annotations

import pytest
from django.urls import reverse

from catalog.etl.belimo_analogs import (
    belimo_codes_for_sku,
    extract_belimo_codes_from_text,
    infer_belimo_codes,
    normalize_belimo_code,
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
    """Fire SA*FU without card text → Belimo BF/BFN/BFS by torque."""
    assert infer_belimo_codes(
        purpose="fire_spring",
        moment_nm=5.0,
        voltage="24",
        control="on_off",
        aux_spdt=1,
        thermal=False,
    ) == ["BF24-S"]
    assert infer_belimo_codes(
        purpose="fire_spring",
        moment_nm=10.0,
        voltage="230",
        control="on_off",
        aux_spdt=0,
        thermal=True,
    ) == ["BFN230-T"]


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


@pytest.mark.django_db
def test_belimo_codes_for_sku_infers_when_text_empty() -> None:
    """Missing analogs_text → infer from EAV + category."""
    cat = Category.objects.create(
        name="Air no spring",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(name="HVD", slug="hvd-analog-test", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="HVD24-5",
        slug="hvd24-5-analog-test",
        sku_code="HVD24-5",
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
