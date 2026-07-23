"""Tests for SKU variant parsing and description scoping."""

from __future__ import annotations

from catalog.etl.sku_variant import (
    filter_description_for_variant,
    parse_sku_variant,
)

SAMPLE = """Лид про серию.

Электрические параметры

Диапазон напряжения для:

– 24 В: 19,2−28,8 В
– 230 В: 85−250 В

– Работают от AC/DC 24V или AC 100...240V (50/60 Гц).

DA3FU24-D/DS:

– Напряжение питания: AC/DC 24В, 50/60 Гц
– Класс защиты: III

DA3FU230-D/DS:

– Напряжение питания: AC 100...240В, 50/60 Гц
– Класс защиты: II
"""


def test_parse_sku_variant_voltage_and_control() -> None:
    """Edition suffixes drive voltage / control / aux flags."""
    v = parse_sku_variant("da3fu230-d")
    assert v.voltage == "230"
    assert v.control == "on_off"
    assert v.aux_switch is False

    v24 = parse_sku_variant("da10fu24-as")
    assert v24.voltage == "24"
    assert v24.control == "modulating"
    assert v24.aux_switch is True

    dst = parse_sku_variant("sa10mu24-dst")
    assert dst.voltage == "24"
    assert dst.control == "on_off"
    assert dst.aux_switch is True


def test_parse_sku_variant_ignores_non_terminal_suffix_lookalikes() -> None:
    """Suffix tags must match only at the very end of sku_code."""
    variant = parse_sku_variant("da3fu230-as1")
    assert variant.control is None
    assert variant.aux_switch is None

    variant = parse_sku_variant("da3fu230-d5")
    assert variant.control is None
    assert variant.aux_switch is None

    variant = parse_sku_variant("da3fu230-ds-extra")
    assert variant.control is None
    assert variant.aux_switch is None


def test_filter_description_keeps_matching_electrical_block() -> None:
    """230 V SKU keeps only DA3FU230 block and 230 range bullet."""
    out = filter_description_for_variant(SAMPLE, parse_sku_variant("da3fu230-d"))
    assert "DA3FU230-D:" in out
    assert "D/DS" not in out
    assert "DA3FU24" not in out
    assert "230 В: 85" in out
    assert "24 В: 19" not in out
    assert "Работает от AC 100" in out
    assert "или AC 100" not in out


def test_filter_description_24v_variant() -> None:
    """24 V SKU keeps DA3FU24 block only."""
    out = filter_description_for_variant(SAMPLE, parse_sku_variant("da3fu24-ds"))
    assert "DA3FU24-DS:" in out
    assert "DA3FU230" not in out
    assert "24 В: 19" in out


def test_filter_description_section_header_does_not_end_skip() -> None:
    """Generic «Характеристики:» must not leak content from a dropped edition."""
    text = """Лид.

DA3FU230-D/DS:
– Напряжение: 230 В

DA3FU24-D/DS:
– Напряжение: 24 В
Характеристики:
– Утечка чужого блока
– Ещё утечка
"""
    out = filter_description_for_variant(text, parse_sku_variant("da3fu230-d"))
    assert "DA3FU230-D:" in out
    assert "230 В" in out
    assert "Характеристики" not in out
    assert "Утечка" not in out
    assert "DA3FU24" not in out
    assert "24 В" not in out


def test_rewrite_dual_voltage_model_mask() -> None:
    """DA3FU24/230-D/DS becomes the concrete edition from the SKU code."""
    from catalog.etl.sku_variant import rewrite_series_tokens_for_variant

    line = "– DA3FU24/230-D/DS (3 Нм) — до 0,3 м²."
    out_230 = rewrite_series_tokens_for_variant(line, parse_sku_variant("da3fu230-d"))
    assert "DA3FU230-D" in out_230
    assert "24/230" not in out_230
    assert "D/DS" not in out_230

    out_24 = rewrite_series_tokens_for_variant(line, parse_sku_variant("da3fu24-ds"))
    assert "DA3FU24-DS" in out_24
    assert "24/230" not in out_24

    paren = rewrite_series_tokens_for_variant(
        "модель DA3FU24(230)-D(S)",
        parse_sku_variant("da3fu230-ds"),
    )
    assert "DA3FU230-DS" in paren


def test_filter_images_drops_opposite_control_alts() -> None:
    """D/DS gallery drops «плавное»; A/AS drops «открыто/закрыто»."""
    from types import SimpleNamespace

    from catalog.etl.sku_variant import filter_images_for_variant

    gallery = [
        SimpleNamespace(alt="DA5FU | 5 Нм Привод (da5fu24-d)"),
        SimpleNamespace(alt="привод с типом управления плавное, 5 Нм"),
        SimpleNamespace(alt="подключение типом управления открыто/закрыто, 5 Нм"),
        SimpleNamespace(alt="подключение типом управления плавное, 5 Нм"),
        SimpleNamespace(alt="Монтажная схема, крутящий момент 5 Нм"),
    ]
    on_off = filter_images_for_variant(gallery, parse_sku_variant("da5fu24-d"))
    assert [img.alt for img in on_off] == [
        gallery[0].alt,
        gallery[2].alt,
        gallery[4].alt,
    ]

    modulating = filter_images_for_variant(gallery, parse_sku_variant("da5fu24-a"))
    assert [img.alt for img in modulating] == [
        gallery[0].alt,
        gallery[1].alt,
        gallery[3].alt,
        gallery[4].alt,
    ]


def test_filter_images_drops_wrong_torque_alt() -> None:
    """Sibling-series photo with mismatched Нм is not shown."""
    from types import SimpleNamespace

    from catalog.etl.sku_variant import filter_images_for_variant

    gallery = [
        SimpleNamespace(alt="привод открыто/закрыто, крутящий момент 3 Нм"),
        SimpleNamespace(alt="привод открыто/закрыто, крутящий момент 5 Нм"),
    ]
    kept = filter_images_for_variant(gallery, parse_sku_variant("da5fu24-d"))
    assert [img.alt for img in kept] == [gallery[1].alt]


def test_filter_images_drops_sa_thermal_sibling_alt() -> None:
    """Non-DST SA card drops термодатчик shot; DST drops plain area shot."""
    from types import SimpleNamespace

    from catalog.etl.sku_variant import filter_images_for_variant

    gallery = [
        SimpleNamespace(alt="SA5FU | 5 Нм Привод противопожарного клапана (sa5fu24-ds)"),
        SimpleNamespace(
            alt="На изображении привод с термодатчиком на 72 ℃ для противопожарного клапана",
        ),
        SimpleNamespace(
            alt=("На изображении привод для противопожарного клапана максимальная площадь которого: 0,5 м²"),
        ),
    ]
    ds = filter_images_for_variant(gallery, parse_sku_variant("sa5fu24-ds"))
    assert [img.alt for img in ds] == [gallery[0].alt, gallery[2].alt]

    dst_gallery = [
        SimpleNamespace(alt="SA5FU | 5 Нм Привод (sa5fu24-dst)"),
        SimpleNamespace(
            alt=("На изображении привод для противопожарного клапана максимальная площадь которого: 0,5 м²"),
        ),
    ]
    dst = filter_images_for_variant(dst_gallery, parse_sku_variant("sa5fu24-dst"))
    assert [img.alt for img in dst] == [dst_gallery[0].alt]
