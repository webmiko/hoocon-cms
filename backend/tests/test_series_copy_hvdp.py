"""HVD-3P/5P cards take ТТХ from the Russian manuals, not from a neighbour series."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalog.etl.series_copy_hvdp import apply_hvdp_enrichment
from catalog.models import SKU, AttributeValue, Category, ProductFile, ProductImage


def _png() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (40, 30), color=(180, 20, 20)).save(buf, format="PNG")
    return buf.getvalue()


def _pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _manual_tree(root: Path) -> None:
    png = _png()
    for nm in (3, 5):
        folder = root / "assets" / f"hvd-{nm}p"
        folder.mkdir(parents=True)
        for name in ("product.png", "wiring.png", "dimensions.png", "rotation.png", "thermal.png", "aux-diagram.png"):
            (folder / name).write_bytes(png)
        (root / "pdf").mkdir(exist_ok=True)
        (root / "pdf" / f"HVD-{nm}P.pdf").write_bytes(_pdf())


@pytest.mark.django_db
def test_hvdp_cards_follow_ru_manuals(tmp_path: Path) -> None:
    """3 Нм is <75/<25 s and 7×7 shaft; 5 Нм is <70/<20 s and 8×8. S has two aux switches."""
    Category.objects.create(
        name="С пружиной",
        slug="elektroprivody-s-pruzhinnym-vozvratom",
    )
    _manual_tree(tmp_path)

    stats = apply_hvdp_enrichment(
        dry_run=False,
        assets_root=tmp_path / "assets",
        pdf_root=tmp_path / "pdf",
    )
    assert stats["products_created"] == 2
    assert stats["skus_created"] == 8
    assert "error" not in stats

    plain = SKU.objects.get(sku_code="HVD24-3P")
    assert plain.is_published is False
    assert plain.product.slug == "privod-vozdushniy-pruzhina-hvd-3p"
    assert plain.product.category.slug == "elektroprivody-s-pruzhinnym-vozvratom"
    attrs = dict(
        AttributeValue.objects.filter(sku=plain).values_list("attribute__slug", "value"),
    )
    assert attrs["moment"] == "3"
    assert attrs["running-time"] == "< 75 с / возврат пружины < 25 с"
    assert attrs["power-consumption"] == "5 Вт под нагрузкой / 2 Вт в режиме удержания"
    assert attrs["shaft-diameter"] == "круглый 10…16 мм, квадратный 7×7…11×11 мм"
    assert attrs["dimensions"] == "132 × 68,5 × 59"
    assert attrs["weight"] == "< 1,3"
    assert attrs["voltage"] == "AC/DC 24 В, 50/60 Гц"
    assert attrs["protection-class"] == "III (безопасное сверхнизкое напряжение)"
    assert attrs["aux-switch"] == "Нет"
    assert attrs["temp-sensor"] == "Нет"
    assert "SAF72" not in (plain.description or "")

    spring = SKU.objects.get(sku_code="HVD230S-5P")
    spring_attrs = dict(
        AttributeValue.objects.filter(sku=spring).values_list("attribute__slug", "value"),
    )
    assert spring_attrs["moment"] == "5"
    assert spring_attrs["running-time"] == "< 70 с / возврат пружины < 20 с"
    assert spring_attrs["power-consumption"] == "5 Вт под нагрузкой / 3 Вт в режиме удержания"
    assert spring_attrs["shaft-diameter"] == "круглый 10…16 мм, квадратный 8×8…11×11 мм"
    assert spring_attrs["dimensions"] == "158 × 102 × 59"
    assert spring_attrs["weight"] == "< 1,8"
    assert spring_attrs["voltage"] == "AC 100…240 В, 50/60 Гц"
    assert spring_attrs["protection-class"] == "II (полная изоляция)"
    assert spring_attrs["aux-switch"] == "SPDT-2"
    assert spring.is_published is False

    hero = ProductImage.objects.get(sku=plain, sort_order=0, is_published=True)
    assert "фото привода" in hero.alt
    assert hero.alt.startswith("HVD24-3P")
    stop = ProductImage.objects.get(sku=plain, source_url__contains="angle-stop")
    assert "упор угла" in stop.alt
    assert ProductImage.objects.filter(sku=plain, source_url__contains="-aux.").exists() is False
    assert ProductImage.objects.filter(sku=spring, source_url__contains="-aux.").exists()
    assert ProductFile.objects.filter(sku=plain, title="Инструкция HVD-3P").exists()
    assert ProductFile.objects.filter(sku=spring, title="Инструкция HVD-5P").exists()

    again = apply_hvdp_enrichment(
        dry_run=False,
        assets_root=tmp_path / "assets",
        pdf_root=tmp_path / "pdf",
    )
    assert again["products_created"] == 0
    assert again["skus_created"] == 0
    assert again["pdfs"] == 0
    assert SKU.objects.filter(sku_code__iendswith="p").count() == 8
