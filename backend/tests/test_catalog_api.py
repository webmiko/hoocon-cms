"""Tests for public catalog API (TDD: red → green → refactor).

Spec: docs/readiness-backend-ux.md §2.3; docs/security-baseline.md §3.2
(цены скрыты по умолчанию); ПЛАН §6 Iter 1 — list/detail + filters,
без утечки цен.

Endpoints:
  GET /api/catalog/categories/
  GET /api/catalog/skus/
  GET /api/catalog/skus/{slug}/
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse


def _seed_catalog():
    """Category → Product → SKU(+price) → AttributeValue → ProductFile."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
        ProductFile,
    )

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie")
    product = Product.objects.create(name="HVA", slug="hva", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="Привод HVA 5NM",
        slug="privod-hva-5nm",
        sku_code="HVA-5NM",
        price=Decimal("1234.50"),
        is_published=True,
    )
    unpublished = SKU.objects.create(
        product=product,
        name="Draft",
        slug="draft-sku",
        sku_code="DRAFT-1",
        price=Decimal("99.00"),
        is_published=False,
    )
    moment = Attribute.objects.create(name="Момент", slug="moment", unit="Н·м")
    AttributeValue.objects.create(sku=sku, attribute=moment, value="5")
    pdf = SimpleUploadedFile(
        "d.pdf",
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0" * 32,
        content_type="application/pdf",
    )
    ProductFile.objects.create(
        sku=sku,
        title="Паспорт",
        file=pdf,
        file_type=ProductFile.FileType.DATASHEET,
    )
    return {"cat": cat, "product": product, "sku": sku, "unpublished": unpublished}


@pytest.mark.django_db
def test_sku_list_returns_only_published(client) -> None:
    """List endpoint omits unpublished SKUs."""
    _seed_catalog()
    url = reverse("catalog-sku-list")
    response = client.get(url)
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert "privod-hva-5nm" in slugs
    assert "draft-sku" not in slugs


@pytest.mark.django_db
def test_sku_detail_by_slug(client) -> None:
    """Detail is looked up by slug (canonical SEO path)."""
    seed = _seed_catalog()
    url = reverse("catalog-sku-detail", kwargs={"slug": seed["sku"].slug})
    response = client.get(url)
    assert response.status_code == 200
    assert response.data["sku_code"] == "HVA-5NM"
    assert response.data["slug"] == "privod-hva-5nm"


@pytest.mark.django_db
def test_sku_detail_ball_valve_kit_for_bv_sku(client) -> None:
    """Ball-valve detail exposes RFQ kit options when drives are known."""
    from catalog.etl.attr_write import set_sku_attribute
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    product = Product.objects.create(
        name="BV220",
        slug="sharovoy-kran-bv220",
        category=cat,
    )
    sku = SKU.objects.create(
        product=product,
        name="BV220A",
        slug="8100-bv220a",
        sku_code="8100-BV220A",
        is_published=True,
    )
    set_sku_attribute(
        sku,
        slug="compatible-actuators",
        value="DA5FU24, DA6MU24 (−D/−DS/−A/−AS)",
        name="Совместимый привод",
        unit="",
    )

    url = reverse("catalog-sku-detail", kwargs={"slug": sku.slug})
    response = client.get(url)
    assert response.status_code == 200
    kit = response.data["ball_valve_kit"]
    assert kit is not None
    assert kit["drive_families"] == ["DA5FU24", "DA6MU24"]
    assert kit["bracket_by_drive"]["DA5FU24"] == "BR-ML"
    assert kit["bracket_by_drive"]["DA6MU24"] == "BR-M"


@pytest.mark.django_db
def test_sku_detail_ball_valve_kit_null_for_actuator(client) -> None:
    """Non ball-valve SKUs do not expose kit picker payload."""
    seed = _seed_catalog()
    url = reverse("catalog-sku-detail", kwargs={"slug": seed["sku"].slug})
    response = client.get(url)
    assert response.status_code == 200
    assert response.data["ball_valve_kit"] is None


@pytest.mark.django_db
def test_sku_detail_includes_attributes_and_files(client) -> None:
    """Detail payload includes ТТХ and published PDF metadata."""
    seed = _seed_catalog()
    url = reverse("catalog-sku-detail", kwargs={"slug": seed["sku"].slug})
    response = client.get(url)
    assert response.status_code == 200
    attrs = {a["slug"]: a["value"] for a in response.data["attributes"]}
    assert attrs["moment"] == "5"
    assert len(response.data["files"]) == 1
    assert response.data["files"][0]["title"] == "Паспорт"
    assert "file" in response.data["files"][0]


@pytest.mark.django_db
def test_sku_list_hides_price_when_show_prices_false(client) -> None:
    """Security: no price leak when SiteSettings.show_prices_on_site is False."""
    from sitesettings.models import SiteSettings

    _seed_catalog()
    settings = SiteSettings.load()
    settings.show_prices_on_site = False
    settings.save()

    response = client.get(reverse("catalog-sku-list"))
    assert response.status_code == 200
    row = response.data["results"][0]
    assert "price" not in row
    assert row.get("price_on_request") is True
    # Nested dump must not contain the numeric price either.
    body = response.content.decode()
    assert "1234.50" not in body
    assert "1234.5" not in body


@pytest.mark.django_db
def test_sku_detail_hides_price_when_show_prices_false(client) -> None:
    """Security: detail also hides price by default."""
    from sitesettings.models import SiteSettings

    seed = _seed_catalog()
    settings = SiteSettings.load()
    settings.show_prices_on_site = False
    settings.save()

    url = reverse("catalog-sku-detail", kwargs={"slug": seed["sku"].slug})
    response = client.get(url)
    assert response.status_code == 200
    assert "price" not in response.data
    assert response.data.get("price_on_request") is True
    assert "1234.50" not in response.content.decode()


@pytest.mark.django_db
def test_sku_list_shows_price_when_flag_enabled(client) -> None:
    """When show_prices_on_site=True, price is present for staff/public API."""
    from sitesettings.models import SiteSettings

    _seed_catalog()
    settings = SiteSettings.load()
    settings.show_prices_on_site = True
    settings.save()

    response = client.get(reverse("catalog-sku-list"))
    row = response.data["results"][0]
    assert row["price"] == "1234.50"
    assert row.get("price_on_request") is False


@pytest.mark.django_db
def test_sku_filter_by_attribute_slug(client) -> None:
    """?moment=5 filters SKUs via EAV AttributeValue exact match."""
    seed = _seed_catalog()
    # Second SKU with different moment — must be excluded by filter.
    from catalog.models import SKU, Attribute, AttributeValue

    other = SKU.objects.create(
        product=seed["product"],
        name="HVA 10NM",
        slug="privod-hva-10nm",
        sku_code="HVA-10NM",
        is_published=True,
    )
    moment = Attribute.objects.get(slug="moment")
    AttributeValue.objects.create(sku=other, attribute=moment, value="10")

    response = client.get(reverse("catalog-sku-list"), {"moment": "5"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert slugs == {"privod-hva-5nm"}


@pytest.mark.django_db
def test_sku_filter_by_category_slug(client) -> None:
    """?category=<slug> filters by product.category.slug."""
    _seed_catalog()
    response = client.get(
        reverse("catalog-sku-list"),
        {"category": "vozdushnie"},
    )
    assert response.status_code == 200
    assert len(response.data["results"]) == 1

    empty = client.get(reverse("catalog-sku-list"), {"category": "nope"})
    assert empty.data["results"] == []


@pytest.mark.django_db
def test_sku_search_q_matches_sku_code(client) -> None:
    """?q= searches name / sku_code / slug (icontains; FTS — Iter 2)."""
    _seed_catalog()
    response = client.get(reverse("catalog-sku-list"), {"q": "HVA-5"})
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["sku_code"] == "HVA-5NM"


@pytest.mark.django_db
def test_category_list(client) -> None:
    """GET /api/catalog/categories/ returns seeded categories."""
    _seed_catalog()
    response = client.get(reverse("catalog-category-list"))
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert "vozdushnie" in slugs


@pytest.mark.django_db
def test_sku_list_follows_category_filter_order(client) -> None:
    """Catalog cards appear in the same category order as the filter sidebar."""
    from catalog.models import SKU, Category, Product
    from catalog.series_categories import spec_categories

    specs = spec_categories()
    # Seed last → first so sku_code order would invert category order.
    for spec in reversed(specs):
        cat = Category.objects.create(name=spec.name, slug=spec.slug)
        product = Product.objects.create(
            name=f"P-{spec.slug}",
            slug=f"p-{spec.slug}",
            category=cat,
        )
        SKU.objects.create(
            product=product,
            name=f"SKU {spec.slug}",
            slug=f"sku-{spec.slug}",
            sku_code=f"Z-{spec.sort_order:02d}",
            is_published=True,
        )

    cats = client.get(reverse("catalog-category-list"))
    assert cats.status_code == 200
    cat_slugs = [row["slug"] for row in cats.data["results"]]

    skus = client.get(reverse("catalog-sku-list"), {"page_size": 100})
    assert skus.status_code == 200
    seen: list[str] = []
    for row in skus.data["results"]:
        slug = row["category_slug"]
        if slug not in seen:
            seen.append(slug)

    assert seen == cat_slugs
    assert seen == [s.slug for s in specs]


@pytest.mark.django_db
def test_sku_list_orders_by_moment_numeric_not_sku_code(client) -> None:
    """Within a category, cards sort 2 → 10 → 32 Нм (not da10, da2, da32)."""
    from catalog.models import SKU, Attribute, AttributeValue, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="elektroprivody-vozdushnye")
    product = Product.objects.create(name="P-moment", slug="p-moment-sort", category=cat)
    moment = Attribute.objects.create(name="Крутящий момент", slug="moment", unit="Нм")
    # Lexicographic sku_code order would be da10, da2, da32 — wrong for torque.
    for code, nm in (("da32mu24", "32 Нм"), ("da10mu24", "10 Нм"), ("da2mu24", "2 Нм")):
        sku = SKU.objects.create(
            product=product,
            name=code.upper(),
            slug=f"sku-{code}",
            sku_code=code,
            is_published=True,
        )
        AttributeValue.objects.create(sku=sku, attribute=moment, value=nm)

    response = client.get(
        reverse("catalog-sku-list"),
        {"category": cat.slug, "page_size": 20},
    )
    assert response.status_code == 200
    codes = [row["sku_code"] for row in response.data["results"]]
    assert codes == ["da2mu24", "da10mu24", "da32mu24"]


@pytest.mark.django_db
def test_sku_list_orders_category_then_moment(client) -> None:
    """All-categories list: sidebar category order, then torque inside each."""
    from catalog.models import SKU, Attribute, AttributeValue, Category, Product
    from catalog.series_categories import spec_categories

    specs = [s for s in spec_categories() if s.slug != "sharovye-krany"][:2]
    assert len(specs) == 2
    moment = Attribute.objects.create(name="Крутящий момент", slug="moment", unit="Нм")
    # Earlier category gets higher torque so sku_code/moment alone would invert.
    for spec, nm, code in (
        (specs[0], "32 Нм", "zz-early-32"),
        (specs[1], "2 Нм", "aa-late-2"),
    ):
        cat = Category.objects.create(name=spec.name, slug=spec.slug)
        product = Product.objects.create(
            name=f"P-{spec.slug}",
            slug=f"p-{spec.slug}-mom",
            category=cat,
        )
        sku = SKU.objects.create(
            product=product,
            name=code,
            slug=f"sku-{code}",
            sku_code=code,
            is_published=True,
        )
        AttributeValue.objects.create(sku=sku, attribute=moment, value=nm)

    response = client.get(reverse("catalog-sku-list"), {"page_size": 50})
    assert response.status_code == 200
    codes = [row["sku_code"] for row in response.data["results"]]
    assert codes.index("zz-early-32") < codes.index("aa-late-2")


@pytest.mark.django_db
def test_category_list_includes_preview_image(client) -> None:
    """Category payload includes first published product photo when present."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from catalog.models import ProductImage

    seed = _seed_catalog()
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    ProductImage.objects.create(
        sku=seed["sku"],
        image=SimpleUploadedFile("t.png", png, content_type="image/png"),
        alt="HVA preview",
        is_published=True,
        sort_order=0,
    )
    response = client.get(reverse("catalog-category-list"))
    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["slug"] == "vozdushnie")
    assert row["image"] is not None
    assert "image" in row["image"]
    assert row["image"]["alt"] == "HVA preview"


@pytest.mark.django_db
def test_ball_valves_category_prefers_dn40_preview(client) -> None:
    """Homepage tile for шаровые краны uses DN 40 (BV240), not the first DN 15."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from catalog.models import SKU, Category, Product, ProductImage

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    product = Product.objects.create(name="BV", slug="bv-series", category=cat)
    sku_dn15 = SKU.objects.create(
        product=product,
        name="BV215 DN15",
        slug="8100-bv215a",
        sku_code="8100-bv215a",
        is_published=True,
    )
    sku_dn40 = SKU.objects.create(
        product=product,
        name="BV240 DN40",
        slug="8100-bv240a",
        sku_code="8100-bv240a",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=sku_dn15,
        image=SimpleUploadedFile("dn15.png", png, content_type="image/png"),
        alt="DN 15",
        is_published=True,
        sort_order=0,
    )
    ProductImage.objects.create(
        sku=sku_dn40,
        image=SimpleUploadedFile("dn40.png", png, content_type="image/png"),
        alt="DN 40",
        is_published=True,
        sort_order=0,
    )

    response = client.get(reverse("catalog-category-list"))
    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["slug"] == "sharovye-krany")
    assert row["image"] is not None
    assert row["image"]["alt"] == "DN 40"


@pytest.mark.django_db
def test_sku_list_is_read_only_for_anon(client) -> None:
    """Public API is read-only: POST → 405."""
    _seed_catalog()
    response = client.post(
        reverse("catalog-sku-list"),
        {"name": "hack", "slug": "hack", "sku_code": "HACK"},
        content_type="application/json",
    )
    assert response.status_code == 405


@pytest.mark.django_db
def test_unpublished_sku_detail_is_404(client) -> None:
    """Unpublished SKU is not reachable by slug on public API."""
    seed = _seed_catalog()
    url = reverse(
        "catalog-sku-detail",
        kwargs={"slug": seed["unpublished"].slug},
    )
    response = client.get(url)
    assert response.status_code == 404
