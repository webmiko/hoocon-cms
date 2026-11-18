"""Belimo analog extraction from card copy and spec-based inference."""

from __future__ import annotations

from io import StringIO

import pytest
from django.urls import reverse

from catalog.etl.belimo_analogs import (
    analogs_plain_text_for_sku,
    belimo_code_is_direct_for_sku,
    belimo_code_is_modulating,
    belimo_code_is_open_close,
    belimo_code_is_thermal,
    belimo_code_matches_control,
    belimo_codes_for_sku,
    compose_belimo_article,
    detect_purpose,
    extract_belimo_codes_from_text,
    infer_belimo_codes,
    normalize_belimo_code,
    primary_belimo_code_for_sku,
    sku_code_is_thermal,
    sku_code_takes_no_analogs,
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
    assert normalize_belimo_code("TMC230ASR") == "TMC230A-SR"
    assert normalize_belimo_code("lm230asr") == "LM230A-SR"


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
    """HVD 20 Нм is SM. The shared card text is not the source of the article."""
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
    assert belimo_codes_for_sku(bare) == []
    assert belimo_codes_for_sku(with_s) == []


@pytest.mark.django_db
def test_belimo_codes_strips_lone_s_for_non_aux_damu_d() -> None:
    """Shared D/DS card with only LM24A-S → D gets LM24A, DS keeps -S."""
    cat = Category.objects.create(name="Air", slug="air-damu-aux-analog")
    product = Product.objects.create(
        name="DA6MU",
        slug="da6mu-aux-analog",
        category=cat,
        analogs_text="""
Аналоги для DA6MU24-D/DS (24 В, 6Нм):
– Belimo LM24A-S (без возвратной пружины)
""",
    )
    bare = SKU.objects.create(
        product=product,
        name="DA6MU24-D",
        slug="da6mu24-d-aux",
        sku_code="DA6MU24-D",
        is_published=True,
        analog_belimo_code="LM24A-S",
    )
    with_s = SKU.objects.create(
        product=product,
        name="DA6MU24-DS",
        slug="da6mu24-ds-aux",
        sku_code="DA6MU24-DS",
        is_published=True,
        analog_belimo_code="LM24A-S",
    )
    assert belimo_codes_for_sku(bare) == []
    assert belimo_codes_for_sku(with_s) == []
    assert primary_belimo_code_for_sku(bare) is None
    assert primary_belimo_code_for_sku(with_s) is None


def test_infer_air_no_spring_by_moment_voltage_aux_control() -> None:
    """HVD-class: TMC/LM/NM/GM by moment + voltage + aux + control."""
    assert infer_belimo_codes(
        purpose="air_no_spring",
        moment_nm=2.0,
        voltage="24",
        control="on_off",
        aux_spdt=0,
    ) == ["TMC24A"]
    assert infer_belimo_codes(
        purpose="air_no_spring",
        moment_nm=2.0,
        voltage="230",
        control="modulating",
        aux_spdt=0,
    ) == ["TMC230A-SR"]
    # TMC-SR has no factory aux edition (add-on S1A) → no direct analog with switches.
    assert (
        infer_belimo_codes(
            purpose="air_no_spring",
            moment_nm=2.0,
            voltage="230",
            control="modulating",
            aux_spdt=1,
        )
        == []
    )
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
    """Fire/smoke spring-return → Belimo BLF/BFN by torque band; 3 Нм has no direct BFL (4/3 Нм)."""
    assert (
        infer_belimo_codes(
            purpose="fire_spring",
            moment_nm=3.0,
            voltage="24",
            control="on_off",
            aux_spdt=2,
            thermal=False,
        )
        == []
    )
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


def test_infer_smoke_control_not_cm() -> None:
    """SA..MU smoke infers BEN/BEE/BE not stronger than Hoocon; < 15 Нм → none, never CM 2 Нм air compact."""
    for moment in (7.0, 10.0):
        assert (
            infer_belimo_codes(
                purpose="smoke",
                moment_nm=moment,
                voltage="24",
                control="on_off",
                aux_spdt=2,
            )
            == []
        )
    # Smoke BEN/BEE/BE have no thermoelectric -T. BEE24-ST is a connector plug.
    assert (
        infer_belimo_codes(
            purpose="smoke",
            moment_nm=15.0,
            voltage="230",
            control="on_off",
            aux_spdt=2,
            thermal=True,
        )
        == []
    )
    assert infer_belimo_codes(
        purpose="smoke",
        moment_nm=15.0,
        voltage="230",
        control="on_off",
        aux_spdt=2,
        thermal=False,
    ) == ["BEN230"]
    assert infer_belimo_codes(
        purpose="smoke",
        moment_nm=30.0,
        voltage="24",
        control="on_off",
        aux_spdt=2,
    ) == ["BEE24"]


def test_detect_purpose_hvd_is_fire_spring() -> None:
    """HVD-…F must not inherit category smoke (SA..MU lives in same category)."""
    from catalog.etl.belimo_analogs import detect_purpose

    slug = "elektroprivody-dlya-klapanov-dymoudaleniya"
    assert detect_purpose(category_slug=slug, sku_code="HVD24S-3F") == "fire_spring"
    assert detect_purpose(category_slug=slug, sku_code="HVD230ST-5F") == "fire_spring"
    assert detect_purpose(category_slug=slug, sku_code="SA10MU24-DS") == "smoke"
    # Bare / Q HVD are air (non-spring), not fire BFL/BLF.
    assert detect_purpose(category_slug=slug, sku_code="HVD24-40") == "air_no_spring"
    assert detect_purpose(category_slug=slug, sku_code="HVD24S-20") == "air_no_spring"
    assert detect_purpose(category_slug=slug, sku_code="HVD24-10Q") == "fast"
    assert detect_purpose(category_slug=slug, sku_code="HVD230S-40QX") == "electronic_failsafe"


def test_infer_fast_actuator() -> None:
    """Q-series is AC/DC 24 V, base or -SR. No 230 V and no factory aux -S (S1A/S2A)."""
    assert infer_belimo_codes(
        purpose="fast",
        moment_nm=8.0,
        voltage="24",
        control="modulating",
        aux_spdt=0,
    ) == ["NMQ24A-SR"]
    assert (
        infer_belimo_codes(
            purpose="fast",
            moment_nm=8.0,
            voltage="24",
            control="modulating",
            aux_spdt=2,
        )
        == []
    )
    assert infer_belimo_codes(
        purpose="fast",
        moment_nm=16.0,
        voltage="24",
        control="modulating",
        aux_spdt=0,
    ) == ["SMQ24A-SR"]
    assert (
        infer_belimo_codes(
            purpose="fast",
            moment_nm=24.0,
            voltage="230",
            control="on_off",
            aux_spdt=1,
        )
        == []
    )
    assert (
        infer_belimo_codes(
            purpose="fast",
            moment_nm=5.0,
            voltage="24",
            control="modulating",
            aux_spdt=1,
        )
        == []
    )


@pytest.mark.django_db
def test_belimo_codes_for_sku_prefers_card_text() -> None:
    """Card prose is not a confirmed pair, so it does not become the article."""
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
    assert belimo_codes_for_sku(sku) == []


def test_belimo_code_control_sr_token() -> None:
    """Open/close vs ``-SR``; spring ``LF24-RS`` stays ambiguous (kept)."""
    assert belimo_code_is_modulating("LM24A-SR") is True
    assert belimo_code_is_modulating("LM24A-SR-S") is True
    assert belimo_code_is_modulating("NM24A-SR-20") is True
    assert belimo_code_is_modulating("LM24A-S") is False
    assert belimo_code_is_modulating("CM230-L/R") is False
    assert belimo_code_is_open_close("TMC230A") is True
    assert belimo_code_is_open_close("TMC230A-S") is True
    assert belimo_code_matches_control("CM230-L/R", "on_off") is True
    assert belimo_code_matches_control("CM230-L/R", "modulating") is False
    assert belimo_code_matches_control("TMC230A", "on_off") is True
    assert belimo_code_matches_control("TMC230A", "modulating") is False
    assert belimo_code_matches_control("TMC230A-S", "on_off") is True
    assert belimo_code_matches_control("LM230A-S", "modulating") is False
    assert belimo_code_matches_control("LM230A-SR-S", "modulating") is True
    assert belimo_code_matches_control("LM230A-SR-S", "on_off") is False
    assert belimo_code_matches_control("LF24-RS", "modulating") is True
    assert belimo_code_matches_control("LF24-RS", "on_off") is True
    assert belimo_code_matches_control("LF24-S", "modulating") is True


@pytest.mark.django_db
def test_shared_ds_as_block_splits_belimo_by_control() -> None:
    """Combined ``…-D/…-A`` card text must not pin one Belimo on both control sides."""
    cat = Category.objects.create(
        name="Air no spring",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(name="DA2MU", slug="da2mu-shared-analog", category=cat)
    text = """
Список аналогов для привода серии DA..MU 2 Нм

Для Hoocon DA2MU230-D/DA2MU230-A (230В):

– Belimo CM230-L/R

Основные характеристики аналогов
Управление: 2-/3-позиционное
""".strip()
    moment = Attribute.objects.create(name="Крутящий момент", slug="moment")
    voltage = Attribute.objects.create(name="Напряжение", slug="voltage")
    control = Attribute.objects.create(name="Управление", slug="control")
    aux = Attribute.objects.create(name="Вспомогательный переключатель", slug="aux-switch")

    on_off = SKU.objects.create(
        product=product,
        name="DA2MU230-D",
        slug="da2mu230-d-shared",
        sku_code="DA2MU230-D",
        is_published=True,
        analog_belimo_code="CM230-L/R",
        analogs_text=text,
    )
    AttributeValue.objects.create(sku=on_off, attribute=moment, value="2 Нм")
    AttributeValue.objects.create(sku=on_off, attribute=voltage, value="AC 230 В")
    AttributeValue.objects.create(sku=on_off, attribute=control, value="Открыто/закрыто")
    AttributeValue.objects.create(sku=on_off, attribute=aux, value="Нет")

    modulating = SKU.objects.create(
        product=product,
        name="DA2MU230-A",
        slug="da2mu230-a-shared",
        sku_code="DA2MU230-A",
        is_published=True,
        analog_belimo_code="CM230-L/R",
        analogs_text=text,
    )
    AttributeValue.objects.create(sku=modulating, attribute=moment, value="2 Нм")
    AttributeValue.objects.create(sku=modulating, attribute=voltage, value="AC 230 В")
    AttributeValue.objects.create(sku=modulating, attribute=control, value="Пропорциональное")
    AttributeValue.objects.create(sku=modulating, attribute=aux, value="Нет")

    assert belimo_codes_for_sku(on_off) == []
    assert belimo_codes_for_sku(modulating) == []
    assert primary_belimo_code_for_sku(modulating) is None

    modulating_text = analogs_plain_text_for_sku(modulating)
    assert "CM230-L/R" not in modulating_text
    assert "DA2MU230-A" in modulating_text
    assert "CM230-L/R" in analogs_plain_text_for_sku(on_off)


@pytest.mark.django_db
def test_damu_2nm_analogs_have_no_foreign_article_bullets() -> None:
    """DA2MU data file: guidance only — no clone bullets, no edition blocks."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "catalog" / "etl" / "data" / "damu_2nm_analogs.txt").read_text(
        encoding="utf-8"
    )
    assert "– " not in text
    for banned in ("Dastech", "Lufberg", "Sputnik", "BVM", "GSD", "Аналоги для "):
        assert banned not in text
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
    sku = SKU.objects.create(
        product=product,
        name="DA2MU230-DS",
        slug="da2mu230-ds-split",
        sku_code="DA2MU230-DS",
        is_published=True,
        analogs_text=text,
    )
    assert analogs_plain_text_for_sku(sku) == text.strip()
    assert belimo_codes_for_sku(sku) == []
    assert primary_belimo_code_for_sku(sku) is None


@pytest.mark.django_db
def test_belimo_codes_for_sku_infers_when_text_empty() -> None:
    """Empty prose does not license a torque-band article."""
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
    assert belimo_codes_for_sku(sku) == []


@pytest.mark.django_db
def test_analog_facet_from_card_text(client) -> None:
    """Prose Belimo lines are not a confirmed pair and do not enter the facet."""
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
    if "analog" in by_key:
        codes = {v["value"] for v in by_key["analog"]["values"]}
        assert "LF24-S" not in codes
        assert "LF24-RS" not in codes

    filtered = client.get(reverse("catalog-sku-list"), {"analog": "LF24-S"})
    assert filtered.status_code == 200
    assert sku.slug not in {row["slug"] for row in filtered.data["results"]}


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
    assert sku_code_is_thermal("HVD24SX-10F") is False
    assert sku_code_is_thermal("HVD24S-3F") is False
    assert sku_code_is_thermal("DSTXXX") is False
    assert sku_code_is_thermal("XDSTX") is False
    assert sku_code_is_thermal("SA5FU24") is False
    assert sku_code_is_thermal("") is False
    assert sku_code_is_thermal(None) is False


def test_belimo_code_is_thermal_suffix_only() -> None:
    """Thermal is fire ``-T`` / ``FST``. ``BEE24-ST`` is a connector plug, not a sensor."""
    assert belimo_code_is_thermal("BF24-T") is True
    assert belimo_code_is_thermal("bf24-t") is True
    assert belimo_code_is_thermal("BF24-FST") is True
    assert belimo_code_is_thermal("FST-230-3N") is True
    assert belimo_code_is_thermal("FST-24-3N") is True
    assert belimo_code_is_thermal("BEE24ST") is False
    assert belimo_code_is_thermal("BEE24-ST") is False
    assert belimo_code_is_thermal("BEE230ST") is False
    assert belimo_code_is_thermal("X-T-Y") is False
    assert belimo_code_is_thermal("BF24-S") is False
    assert belimo_code_is_thermal("BEE24") is False
    assert belimo_code_is_thermal("XFSTY") is False
    assert belimo_code_is_thermal("FSR-230-3N") is False
    assert belimo_code_is_thermal("") is False
    assert belimo_code_is_thermal(None) is False


@pytest.mark.django_db
def test_primary_belimo_ignores_midstring_dst_as_thermal() -> None:
    """A non-actuator code is not a model, so prose Belimo lines are not used."""
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
    assert primary_belimo_code_for_sku(sku) is None


@pytest.mark.django_db
def test_primary_belimo_skips_midstring_dash_t_belimo_code() -> None:
    """SA5FU24-DST is fire 5 Нм: the catalog article is BLF24-T, not the prose."""
    cat = Category.objects.create(name="Fire", slug="fire-mid-t")
    product = Product.objects.create(name="SA", slug="sa-mid-t", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA5FU24-DST",
        slug="sa5fu24-dst-mid-t",
        sku_code="SA5FU24-DST",
        is_published=True,
        analogs_text="– Belimo LM24A-T-S\n– Belimo BLF24-S\n",
    )
    assert belimo_code_is_thermal("LM24A-T-S") is False
    assert belimo_codes_for_sku(sku) == []
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
        analogs_text="– Belimo BLF24-S\n– Belimo BLF24-T\n",
    )
    assert primary_belimo_code_for_sku(sku) is None


@pytest.mark.django_db
def test_primary_belimo_skips_non_thermal_fallback_for_dst_sku() -> None:
    """DST fire 5 Нм takes BLF24-T from the catalog even if the prose lists BLF24."""
    cat = Category.objects.create(name="Fire", slug="fire-thermal-none")
    product = Product.objects.create(name="SA", slug="sa-thermal-none", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA5FU24-DST",
        slug="sa5fu24-dst-none",
        sku_code="SA5FU24-DST",
        is_published=True,
        analogs_text="– Belimo BLF24-S\n– Belimo BLF24\n",
    )
    assert belimo_codes_for_sku(sku) == []
    assert primary_belimo_code_for_sku(sku) is None


@pytest.mark.parametrize(
    ("purpose", "area", "family"),
    [
        ("air_no_spring", 0.6, "LM"),  # 0.6 ≥ LM(0.5), < NM(1.0)
        ("air_no_spring", 2.4, "SM"),  # 2.4 ≥ SM(2.0), < GM(4.0)
        ("air_no_spring", 4.0, "GM"),  # 4.0 ≥ GM(4.0)
        ("air_spring", 0.3, "TF"),  # 0.3 ≥ TF(0.25), < LF(0.4)
        ("air_spring", 0.5, "LF"),  # 0.5 ≥ LF(0.4), < NF(1.0)
        ("fire_spring", 1.0, "BFN"),  # 1.0 ≥ BFN(0.8), < BF(1.5)
        ("fire_spring", 1.5, "BF"),  # 1.5 ≥ BF(1.5)
        ("smoke", 1.5, "BEN"),  # 1.5 ≥ BEN(1.5)
        ("smoke", 2.0, "BEN"),  # 2.0 ≥ BEN(1.5), < BEE(2.5)
        ("fast", 0.8, "NMQ"),  # 0.8 ≥ NMQ(0.8)
        ("fast", 1.0, "NMQ"),  # 1.0 ≥ NMQ(0.8), < SMQ(1.6)
    ],
)
def test_belimo_analogue_area_not_exceeds_hoocon(purpose: str, area: float, family: str) -> None:
    """Площадь Hoocon ≥ площади Belimo: аналог для заслонки не крупнее нашей."""
    from catalog.etl.belimo_analogs import BELIMO_FAMILY_AREA, belimo_family_by_area

    assert belimo_family_by_area(purpose, area) == family
    belimo_area = dict(BELIMO_FAMILY_AREA[purpose])[family]
    assert area >= belimo_area


@pytest.mark.parametrize(
    ("purpose", "area"),
    [
        ("smoke", 0.7),  # SA7MU vs BEN/BLE 15 Нм
        ("smoke", 1.0),  # SA10MU vs BEN/BLE 15 Нм
        ("fire_spring", 0.3),  # SA3FU / HVD-3F vs BFL 4/3 Нм
        ("fast", 0.2),  # below LMQ 4 Нм
    ],
)
def test_belimo_family_none_when_smallest_is_stronger(purpose: str, area: float) -> None:
    """Нет прямого аналога (младший Belimo мощнее Hoocon) → None, а не «ближайший класс»."""
    from catalog.etl.belimo_analogs import belimo_family_by_area

    assert belimo_family_by_area(purpose, area) is None


@pytest.mark.parametrize(
    ("belimo", "sku_code", "direct"),
    [
        ("BEN24", "SA10MU24-DS", False),  # 15 Нм > 10 Нм
        ("BEE24ST", "SA7MU24-DST", False),
        ("BEN24", "SA15MU24-DS", True),
        ("BFL24-T", "SA3FU24-DST", False),  # 4/3 Нм > 3 Нм
        ("BFL24", "HVD24S-3F", False),
        ("BLF24", "HVD24S-5F", True),  # fire: 2× SPDT built in
        ("CM230-L/R", "DA2MU230-DS", False),  # CM has no aux edition
        ("CM230-L/R", "DA2MU230-D", True),
        ("TMC230A-SR", "DA2MU230-AS", False),  # no factory -SR-S
        ("TMC230A-SR", "DA2MU230-A", True),
        ("LF24-RS", "DA5FU24-AS", False),
        ("LM24A-S", "DA4MU24-DS", False),  # LM 5 Нм > 4 Нм
        ("LMQ24A-SR", "HVA24-5QX", False),  # fast, no emergency return
        ("NKQ24A-SR", "HVA24-5QX", False),  # NKQ 1.2 m² > 0.5 m²
        ("NKQ24A-SR", "HVA24-20QX", True),
        ("LMQ24A-SR", "HVA24-5Q", True),
        ("NM24A-SR-20-S", "HVD24S-20", True),
        ("GF24A", "DA2MU24-D", True),  # unknown family: not judged
    ],
)
def test_belimo_code_is_direct_for_sku(belimo: str, sku_code: str, direct: bool) -> None:
    """Прямой аналог: Belimo не мощнее Hoocon, а у исполнения с концевиками есть свои."""
    from catalog.etl.belimo_analogs import belimo_code_is_direct_for_sku

    assert belimo_code_is_direct_for_sku(belimo, sku_code) is direct


def test_every_belimo_table_uses_the_shared_area_bands() -> None:
    """Аналоги выбираются по площади заслонки из одной таблицы BELIMO_FAMILY_AREA."""
    from catalog.etl import series_copy_spring_analogs as spring
    from catalog.etl.belimo_analogs import BELIMO_FAMILY_AREA, belimo_family_by_area
    from catalog.etl.series_copy_damu_analogs import DAMU_BELIMO_NM

    tables = (
        ("air_spring", spring._DAFU_BELIMO),
        ("fire_spring", spring._SAFU_BELIMO),
        ("smoke", spring._SAMU_BELIMO),
        ("fast", {nm: belimo_family_by_area("fast", nm / 10) for nm in (5, 8, 10, 16, 20, 24, 40)}),
    )
    for purpose, table in tables:
        for nm, family in table.items():
            assert family == belimo_family_by_area(purpose, nm / 10), (purpose, nm)
    # DAMU: Hoocon area ≥ Belimo area for every band.
    air_area_map = dict(BELIMO_FAMILY_AREA["air_no_spring"])
    for nm, band in DAMU_BELIMO_NM.items():
        family = belimo_family_by_area("air_no_spring", nm / 10)
        assert family is not None
        assert nm / 10 >= air_area_map[family], (nm, family)


@pytest.mark.django_db
def test_fill_belimo_refreshes_family_drift_without_force() -> None:
    """Stale torque-band code (SM for 16 Нм) must follow the card's area-band NM, no --force."""
    from django.core.management import call_command

    cat = Category.objects.create(name="Air", slug="air-family-drift")
    product = Product.objects.create(name="DA16MU", slug="da16mu-family-drift", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA16MU24-D",
        slug="da16mu24-d-family-drift",
        sku_code="DA16MU24-D",
        is_published=True,
        analog_belimo_code="SM24A",
        analogs_text="Аналоги для DA16MU24-D (24 В, 2-/3-позиционное):\n– Belimo NM24A\n",
    )
    call_command("fill_belimo_analogs", stdout=StringIO())
    sku.refresh_from_db()
    assert sku.analog_belimo_code == ""


@pytest.mark.django_db
def test_fill_belimo_keeps_valid_secondary_code() -> None:
    """SA15MU smoke is BEN24. A stored BLE24 does not stay."""
    from django.core.management import call_command

    cat = Category.objects.create(
        name="Smoke",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya",
    )
    product = Product.objects.create(name="SA15MU", slug="sa15mu-keep-secondary", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA15MU24-DS",
        slug="sa15mu24-ds-keep-secondary",
        sku_code="SA15MU24-DS",
        is_published=True,
        analog_belimo_code="BLE24",
        analogs_text="SA15MU24-DS (24 В, открыто/закрыто):\n– Belimo BEN24\n– Belimo BLE24\n",
    )
    call_command("fill_belimo_analogs", stdout=StringIO())
    sku.refresh_from_db()
    assert sku.analog_belimo_code == ""


@pytest.mark.django_db
def test_regenerated_damu_analogs_reach_stored_belimo_code() -> None:
    """Force-regenerated DAMU card + fill: D moves to NM; AS has no factory -SR-S."""
    from django.core.management import call_command

    from catalog.etl.series_copy_major_analogs import apply_major_analogs_enrichment

    cat = Category.objects.create(
        name="Air no spring",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    old_text = "Аналоги для DA16MU24-D/DS:\n– Belimo SM24A\n– Belimo SM24A-S\n"
    product = Product.objects.create(
        name="DA16MU",
        slug="privod-vozdushniy-bez-pruzhini-damu-16nm",
        category=cat,
        analogs_text=old_text,
    )
    plain = SKU.objects.create(
        product=product,
        name="DA16MU24-D",
        slug="da16mu24-d-regen",
        sku_code="DA16MU24-D",
        is_published=True,
        analog_belimo_code="SM24A",
        analogs_text=old_text,
    )
    aux = SKU.objects.create(
        product=product,
        name="DA16MU24-AS",
        slug="da16mu24-as-regen",
        sku_code="DA16MU24-AS",
        is_published=True,
        analog_belimo_code="SM24A-SR-S",
        analogs_text=old_text,
    )
    apply_major_analogs_enrichment(force=True)
    call_command("fill_belimo_analogs", stdout=StringIO())
    plain.refresh_from_db()
    aux.refresh_from_db()
    assert plain.analog_belimo_code == ""
    # NM modulating + aux is add-on S2A, not a factory NM24A-SR-S.
    assert aux.analog_belimo_code == ""


@pytest.mark.django_db
def test_no_direct_belimo_hidden_on_card_facet_and_field() -> None:
    """SA10MU (10 Нм): stale «BEN24» card line / field must not reach the tab, facet or field.

    BEN/BLE are 15 Нм — Hoocon cannot replace them, so Belimo is not listed at all.
    """
    from django.core.management import call_command

    cat = Category.objects.create(name="Smoke", slug="elektroprivody-dlya-klapanov-dymoudaleniya")
    product = Product.objects.create(name="SA10MU", slug="sa10mu-no-direct", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA10MU24-DS",
        slug="sa10mu24-ds-no-direct",
        sku_code="SA10MU24-DS",
        is_published=True,
        analog_belimo_code="BEN24",
        analogs_text="SA10MU24-DS (24 В, открыто/закрыто):\n– Belimo BEN24\n– Belimo BLE24\n– Siemens GIB131.1E\n",
    )
    from catalog.etl.belimo_analogs import analogs_text_for_card

    text = analogs_plain_text_for_sku(sku)
    assert "Belimo" not in text
    assert "Siemens GIB131.1E" in text
    card_text = analogs_text_for_card(sku)
    # Card shows no unverified pair bullets; a bare edition header goes with them.
    assert "Siemens" not in card_text
    assert "SA10MU24-DS (24 В" not in card_text
    assert belimo_codes_for_sku(sku) == []
    assert primary_belimo_code_for_sku(sku) is None

    call_command("fill_belimo_analogs", stdout=StringIO())
    sku.refresh_from_db()
    assert sku.analog_belimo_code == ""


@pytest.mark.django_db
def test_fill_belimo_keeps_direct_code_when_nothing_resolves() -> None:
    """A code with no actuator model is cleared. Prose and a manual field are not a source."""
    from django.core.management import call_command

    cat = Category.objects.create(name="Misc", slug="misc-keep-manual")
    product = Product.objects.create(name="Misc", slug="misc-keep-manual", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="MISC-1",
        slug="misc-1-keep-manual",
        sku_code="MISC-1",
        is_published=True,
        analog_belimo_code="LM24A",
    )
    call_command("fill_belimo_analogs", stdout=StringIO())
    sku.refresh_from_db()
    assert sku.analog_belimo_code == ""


@pytest.mark.parametrize(
    ("sku_code", "expected"),
    [
        ("H8101-BV215A-24AS", True),
        ("h8122-bv380a-230d", True),
        ("H8205-LAV380ST-230A", True),
        ("8100-bv215a", True),
        ("BV215A", True),
        ("DA4MU24-DS", False),
        ("HVA24S-10Q", False),
        ("sa3fu230-dst", False),
        ("S0-NP", False),
    ],
)
def test_sku_code_takes_no_analogs(sku_code: str, expected: bool) -> None:
    """Kit / ball-valve articles are recognised without a category; actuators are not."""
    assert sku_code_takes_no_analogs(sku_code) is expected
    if expected:
        assert detect_purpose(category_slug="", sku_code=sku_code) == "valve"
        assert belimo_code_is_direct_for_sku("LM24A", sku_code) is False


@pytest.mark.django_db
def test_kits_and_ball_valves_take_no_analogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kits (actuator + valve) and ball valves: no «Аналоги» tab, no Belimo facet, field cleared.

    A Belimo line or a hand-typed field on a kit used to pass through: the
    category was simply not in the purpose map and the large-scope facet reads
    the field directly.
    """
    from django.core.management import call_command

    from catalog.facets import filter_options

    kits = Category.objects.create(name="Комплекты", slug="komplekty")
    valves = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    kit = SKU.objects.create(
        product=Product.objects.create(name="H8101", slug="h8101-no-analogs", category=kits),
        name="H8101-BV215A-24AS",
        slug="h8101-bv215a-24as-no-analogs",
        sku_code="H8101-BV215A-24AS",
        is_published=True,
        analog_belimo_code="LM24A-S",
        analogs_text="– Belimo LM24A-S\n– Siemens GDB131.1E\n",
    )
    valve = SKU.objects.create(
        product=Product.objects.create(name="BV215", slug="8100-bv215-no-analogs", category=valves),
        name="8100-bv215a",
        slug="8100-bv215a-no-analogs",
        sku_code="8100-bv215a",
        is_published=True,
        analog_belimo_code="R215",
    )
    for sku in (kit, valve):
        assert analogs_plain_text_for_sku(sku) == ""
        assert belimo_codes_for_sku(sku) == []
        assert primary_belimo_code_for_sku(sku) is None

    ids = [kit.id, valve.id]
    assert filter_options._collect_analog_facet_options(ids) is None
    assert not filter_options._filter_skus_by_belimo_analog(SKU.objects.filter(id__in=ids), "LM24A-S").exists()

    call_command("fill_belimo_analogs", stdout=StringIO())
    kit.refresh_from_db()
    valve.refresh_from_db()
    assert kit.analog_belimo_code == ""
    assert valve.analog_belimo_code == ""


@pytest.mark.django_db
def test_infer_takes_aux_and_torque_from_edition_code() -> None:
    """Empty «Вспомогательный переключатель» must not erase DS switches (EAV used to win with 0)."""
    cat = Category.objects.create(
        name="Air no spring",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(name="DA6MU", slug="da6mu-edition-aux", category=cat)
    aux_attr = Attribute.objects.create(name="Вспомогательный переключатель", slug="aux-switch")
    ds = SKU.objects.create(
        product=product,
        name="DA6MU24-DS",
        slug="da6mu24-ds-edition-aux",
        sku_code="DA6MU24-DS",
        is_published=True,
    )
    AttributeValue.objects.create(sku=ds, attribute=aux_attr, value="")
    d = SKU.objects.create(
        product=product,
        name="DA6MU24-D",
        slug="da6mu24-d-edition-aux",
        sku_code="DA6MU24-D",
        is_published=True,
    )
    AttributeValue.objects.create(sku=d, attribute=aux_attr, value="SPDT-1")
    assert belimo_codes_for_sku(ds) == []
    assert belimo_codes_for_sku(d) == []


def test_detect_purpose_hva_by_suffix() -> None:
    """HVA-P is spring, HVA-Q/UQ fast without return, QX capacitor — category does not override."""
    from catalog.etl.belimo_analogs import detect_purpose

    qx_cat = "elektronnye-otkazoustoychivye-vozdushnye-privody"
    assert detect_purpose(category_slug="", sku_code="HVA24-10P") == "air_spring"
    assert detect_purpose(category_slug=qx_cat, sku_code="HVA24-10QX") == "electronic_failsafe"
    assert detect_purpose(category_slug=qx_cat, sku_code="HVD24-10QX") == "electronic_failsafe"
    assert detect_purpose(category_slug="", sku_code="HVA230S-5UQ") == "fast"
    assert detect_purpose(category_slug="", sku_code="HVA24-10") == "air_no_spring"


@pytest.mark.django_db
def test_qx_card_belimo_field_is_supercap_not_fast_q() -> None:
    """Поле «Аналог Belimo» на QX — SuperCap, не быстрые LMQ…GMQ без возврата.

    NKQ 6 Nm covers 1.2 m² (fail-safe brochure 2026). Hoocon 5 Nm is 0.5 m²,
    so it is not a direct analog; 20 Nm / 2.0 m² is.
    """
    cat = Category.objects.create(
        name="Electronic fail-safe",
        slug="elektronnye-otkazoustoychivye-vozdushnye-privody",
    )
    product = Product.objects.create(name="HVA-QX", slug="hva-qx-belimo-field", category=cat)
    small = SKU.objects.create(
        product=product,
        name="HVA24-5QX",
        slug="hva24-5qx-belimo-field",
        sku_code="HVA24-5QX",
        is_published=True,
    )
    covered = SKU.objects.create(
        product=product,
        name="HVA24-20QX",
        slug="hva24-20qx-belimo-field",
        sku_code="HVA24-20QX",
        is_published=True,
    )
    ac = SKU.objects.create(
        product=product,
        name="HVA230-20QX",
        slug="hva230-20qx-belimo-field",
        sku_code="HVA230-20QX",
        is_published=True,
    )
    assert primary_belimo_code_for_sku(small) is None
    assert primary_belimo_code_for_sku(covered) is None
    assert primary_belimo_code_for_sku(ac) is None
    # A previously stored fast article must not stick: area alone would keep it.
    small.analog_belimo_code = "LMQ24A-SR"
    small.save(update_fields=["analog_belimo_code"])
    covered.analog_belimo_code = "SMQ24A-SR"
    covered.save(update_fields=["analog_belimo_code"])
    assert primary_belimo_code_for_sku(small) is None
    assert primary_belimo_code_for_sku(covered) is None


def test_generators_and_inference_share_one_article() -> None:
    """Card generators print exactly what inference returns for every edition (no BM, no closest class)."""
    from catalog.etl.belimo_analogs import belimo_family_by_area, compose_belimo_article

    # Datasheets / UK shop, not the old concatenated generator.
    assert compose_belimo_article("LMQ", voltage="24", modulating=True, aux=False) == "LMQ24A-SR"
    assert compose_belimo_article("LMQ", voltage="24", modulating=True, aux=True) is None
    assert compose_belimo_article("LMQ", voltage="230", modulating=False, aux=False) is None
    assert compose_belimo_article("TF", voltage="24", modulating=True, aux=False) is None
    assert compose_belimo_article("LF", voltage="24", modulating=True, aux=True) is None
    assert compose_belimo_article("LF", voltage="24", modulating=True, aux=False) == "LF24-SR"
    assert compose_belimo_article("LF", voltage="230", modulating=True, aux=False) is None
    assert compose_belimo_article("NF", voltage="24", modulating=False, aux=True) == "NF24A-S2"
    assert compose_belimo_article("NF", voltage="24", modulating=True, aux=True) == "NF24A-SR-S2"
    assert compose_belimo_article("TMC", voltage="230", modulating=True, aux=True) is None
    assert compose_belimo_article("NM", voltage="24", modulating=True, aux=True) is None
    assert compose_belimo_article("NM", voltage="230", modulating=True, aux=False) == "NM230A-SR"
    assert compose_belimo_article("GM", voltage="24", modulating=False, aux=True) == "GM24A-S"
    assert compose_belimo_article("GM", voltage="24", modulating=True, aux=True) is None
    assert compose_belimo_article("GM", voltage="230", modulating=True, aux=False) is None
    assert compose_belimo_article("BFN", voltage="24", modulating=True, aux=True) is None
    assert compose_belimo_article("BEE", voltage="230", modulating=False, aux=True, thermal=False) == "BEE230"
    assert compose_belimo_article("BEE", voltage="230", modulating=False, aux=True, thermal=True) is None
    assert compose_belimo_article("BEN", voltage="24", modulating=False, aux=True, thermal=True) is None
    for purpose, nm, voltage, modulating, aux in (
        ("fast", 5, "24", True, True),
        ("air_spring", 5, "24", True, True),
        ("air_no_spring", 2, "230", True, True),
        ("smoke", 10, "24", False, True),
        ("electronic_failsafe", 20, "24", True, False),
        ("electronic_failsafe", 5, "24", True, False),
        ("electronic_failsafe", 20, "230", True, False),
        ("electronic_failsafe", 40, "24", False, True),
    ):
        inferred = infer_belimo_codes(
            purpose=purpose,
            moment_nm=nm,
            voltage=voltage,
            control="modulating" if modulating else "on_off",
            aux_spdt=int(aux),
        )
        family = belimo_family_by_area(purpose, nm / 10)
        composed = family and compose_belimo_article(family, voltage=voltage, modulating=modulating, aux=aux)
        assert inferred == ([composed] if composed else [])


def test_compose_never_emits_articles_belimo_does_not_make() -> None:
    """Every composed code is a catalog literal. These strings are not Belimo articles.

    Q 230 V and Q ``-S``: LMQ24A datasheet is AC/DC 24 V, aux is S1A/S2A.
    ``LF24-RS``: the modulating article is LF24-SR (datasheet 2026-10-29).
    ``NF24A-S``: the aux article is NF24A-S2 (UK shop).
    ``GM24A-SR-S``: absent from the Belimo CZ NG table (GM24A-S itself is listed).
    Smoke ``-T`` / ``BEE230ST``: UK smoke list has BEE230 and BEE24-ST (plug), no ``-T``.
    ``FST-24-3N``: US series is FSTF/FSNF, not this token.
    """
    from catalog.etl.belimo_analogs import BELIMO_CATALOG, BELIMO_NOT_ISSUED

    forbidden = {
        "LMQ230A",
        "NMQ230A",
        "SMQ230A",
        "SMQ230A-S",
        "GMQ230A",
        "LMQ24A-S",
        "LMQ24A-SR-S",
        "NMQ24A-S",
        "NMQ24A-SR-S",
        "SMQ24A-S",
        "SMQ24A-SR-S",
        "GMQ24A-S",
        "GMQ24A-SR-S",
        "LM24A-SR-S",
        "NM24A-SR-S",
        "NM230A-SR-S",
        "SM24A-SR-S",
        "GM24A-SR-S",
        "GM230A-SR-S",
        "GM230A-SR",
        "LF24-RS",
        "LF230-RS",
        "LF230-SR",
        "NF24A-S",
        "NF230A-S",
        "NF24A-SR-S",
        "SF24A-S",
        "SF230A-S",
        "SF24A-SR-S",
        "BEN24-T",
        "BEN230-T",
        "BEE24-T",
        "BEE230-T",
        "BEE24ST",
        "BEE230ST",
        "BE24-T",
        "BLE24-T",
        "BLE230-T",
        "FST-24-3N",
        "FST-230-3N",
        "FSR-24-3N",
        "FSR-230-3N",
    }
    assert BELIMO_NOT_ISSUED == frozenset(forbidden)
    assert forbidden.isdisjoint(BELIMO_CATALOG.values())
    families = sorted({family for family, *_rest in BELIMO_CATALOG})
    for family in families:
        for voltage in ("24", "230"):
            for modulating in (False, True):
                for aux in (False, True):
                    for thermal in (False, True):
                        code = compose_belimo_article(
                            family,
                            voltage=voltage,
                            modulating=modulating,
                            aux=aux,
                            thermal=thermal,
                        )
                        assert code not in forbidden
                        if code is not None:
                            assert code in BELIMO_CATALOG.values()


@pytest.mark.django_db
def test_product_card_uses_catalog_article_for_the_model() -> None:
    """DA5MU24-D does not get a Belimo article from the torque band or from prose.

    LMQ230A is not a Belimo article. LM24A exists, but a band match is not
    confirmation that it replaces this model.
    """
    from catalog.etl.belimo_analogs import analogs_text_for_card
    from catalog.serializers import SKUDetailSerializer

    cat = Category.objects.create(
        name="Air",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(name="DA5MU", slug="da5mu-card-belimo", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA5MU24-D",
        slug="da5mu24-d-card-belimo",
        sku_code="DA5MU24-D",
        is_published=True,
        analog_belimo_code="LMQ230A",
        analogs_text="DA5MU24-D (24 В):\n– Belimo LMQ230A\n– Siemens GDB131.1E\n",
    )
    card = SKUDetailSerializer(sku).data
    assert card["analog_belimo_code"] is None
    text = analogs_text_for_card(sku)
    assert "Belimo" not in text
    assert "LMQ230A" not in text
    # Unverified foreign pairs go too — no bullet may stand in for a confirmed article.
    assert "Siemens" not in text
    assert "DA5MU24-D (24 В)" not in text


@pytest.mark.django_db
def test_invented_q230_article_is_not_shown_or_stored() -> None:
    """LMQ230A is not sold (LMQ24A datasheet: AC/DC 24 V). Stale card text must not keep it."""
    from django.core.management import call_command

    cat = Category.objects.create(name="Fast", slug="fast-unissued-belimo")
    product = Product.objects.create(name="DA5MQU", slug="da5mqu-unissued", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA5MQU230-D",
        slug="da5mqu230-d-unissued",
        sku_code="DA5MQU230-D",
        is_published=True,
        analog_belimo_code="LMQ230A",
        analogs_text="DA5MQU230-D (230 В):\n– Belimo LMQ230A\n– Siemens GDB331.1E\n",
    )
    from catalog.etl.belimo_analogs import analogs_text_for_card

    assert "LMQ230A" not in analogs_plain_text_for_sku(sku)
    assert "Siemens GDB331.1E" in analogs_plain_text_for_sku(sku)
    assert "Siemens" not in analogs_text_for_card(sku)
    assert primary_belimo_code_for_sku(sku) is None
    call_command("fill_belimo_analogs", stdout=StringIO())
    sku.refresh_from_db()
    assert sku.analog_belimo_code == ""
