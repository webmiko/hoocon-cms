"""Catalog list collapses multi-edition family Products to one card."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.family_cards import (
    collapse_family_skus_for_list,
    is_collapsible_family_product_slug,
)
from catalog.models import SKU, Category, Product


@pytest.mark.django_db
def test_is_collapsible_family_product_slug() -> None:
    """H81 / brass / LAV / DAMU / SAMU / SAFU / HVA / HVD collapse; legacy BV do not."""
    assert is_collapsible_family_product_slug("h8101")
    assert is_collapsible_family_product_slug("h8122")
    assert is_collapsible_family_product_slug("8100-bv215")
    assert is_collapsible_family_product_slug("h8205-lav232")
    assert is_collapsible_family_product_slug(
        "privod-vozdushniy-bez-pruzhini-damu-8nm",
    )
    assert is_collapsible_family_product_slug("privod-vozdushniy-da8mqu-8nm")
    assert is_collapsible_family_product_slug(
        "privod-vozdushniy-pruzhina-dafu-10nm",
    )
    assert is_collapsible_family_product_slug("privod-dimoudaleniya-10nm")
    assert is_collapsible_family_product_slug("privod-protivopozharniy-3nm")
    assert is_collapsible_family_product_slug("privod-vozdushniy-hva-5nm")
    assert is_collapsible_family_product_slug(
        "privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-5nm",
    )
    assert is_collapsible_family_product_slug("privod-vozdushniy-hvd-5nm")
    assert is_collapsible_family_product_slug("privod-vozdushniy-hvd-40q")
    assert is_collapsible_family_product_slug("privod-vozdushniy-pruzhina-hva-5p")
    assert is_collapsible_family_product_slug("privod-vozdushniy-kondensator-hvd-10qx")
    assert is_collapsible_family_product_slug("privod-vozdushniy-kondensator-hva-5qx")
    assert is_collapsible_family_product_slug("privod-dimoudaleniya-hvd-3f")
    assert not is_collapsible_family_product_slug("da5fu24")
    assert not is_collapsible_family_product_slug("sharovoy-kran-bv215")
    # Bare prefix must not swallow HVD-F into SAMU Nm.
    assert not is_collapsible_family_product_slug("privod-dimoudaleniya-hvd")
    # Prefix-only matches must not accept stray Product.slug suffixes.
    assert not is_collapsible_family_product_slug("h8205-lav232-variant")
    assert not is_collapsible_family_product_slug("8100-bv215-extra")


@pytest.mark.django_db
def test_collapse_ignores_h8205_and_brass_slug_suffixes() -> None:
    """ORM family_product_q must not treat stray slug suffixes as families."""
    cat = Category.objects.create(name="Комплекты", slug="komplekty")
    weird_lav = Product.objects.create(
        name="LAV stray",
        slug="h8205-lav232-variant",
        category=cat,
    )
    weird_bv = Product.objects.create(
        name="BV stray",
        slug="8100-bv215-extra",
        category=cat,
    )
    canon_lav = Product.objects.create(
        name="LAV canon",
        slug="h8205-lav232",
        category=cat,
    )
    for product, codes in (
        (weird_lav, ("W-LAV-A", "W-LAV-B")),
        (weird_bv, ("W-BV-A", "W-BV-B")),
        (canon_lav, ("H8205-LAV232-24A", "H8205-LAV232-24AS")),
    ):
        for code in codes:
            SKU.objects.create(
                product=product,
                name=code,
                slug=code.lower(),
                sku_code=code,
                is_published=True,
            )

    qs = collapse_family_skus_for_list(SKU.objects.filter(is_published=True))
    codes = sorted(qs.values_list("sku_code", flat=True))
    # Stray-suffix products keep every SKU; canonical LAV collapses to one.
    assert codes == ["H8205-LAV232-24A", "W-BV-A", "W-BV-B", "W-LAV-A", "W-LAV-B"]


@pytest.mark.django_db
def test_collapse_family_skus_keeps_one_per_h81_product() -> None:
    """Within a filtered queryset, one SKU remains per H81 family Product."""
    cat = Category.objects.create(name="Комплекты", slug="komplekty")
    p1 = Product.objects.create(
        name="H8101 | Электрический шаровой кран (стандартная серия)",
        slug="h8101",
        category=cat,
    )
    p2 = Product.objects.create(
        name="H8102 | Электрический шаровой кран (быстродействующая серия)",
        slug="h8102",
        category=cat,
    )
    for code in ("H8101-BV215A-24A", "H8101-BV215A-24AS", "H8101-BV220A-24A"):
        SKU.objects.create(
            product=p1,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )
    SKU.objects.create(
        product=p2,
        name="H8102-BV215A-24A",
        slug="h8102-bv215a-24a",
        sku_code="H8102-BV215A-24A",
        is_published=True,
    )
    qs = collapse_family_skus_for_list(SKU.objects.filter(is_published=True))
    codes = sorted(qs.values_list("sku_code", flat=True))
    assert codes == ["H8101-BV215A-24A", "H8102-BV215A-24A"]


@pytest.mark.django_db
def test_komplekty_list_shows_all_h81_series_cards(client: APIClient) -> None:
    """GET skus/?category=komplekty returns one card per H81 series on page 1."""
    cat = Category.objects.create(name="Комплекты", slug="komplekty")
    for prefix, title in (
        ("H8101", "стандартная"),
        ("H8102", "быстродействующая"),
        ("H8103", "стандартная"),
    ):
        product = Product.objects.create(
            name=f"{prefix} | Электрический шаровой кран ({title} серия)",
            slug=prefix.casefold(),
            category=cat,
        )
        for suffix in ("24A", "24AS", "230A"):
            code = f"{prefix}-BV215A-{suffix}"
            SKU.objects.create(
                product=product,
                name=f"{code} | edition",
                slug=f"{prefix.casefold()}-{code.lower()}",
                sku_code=code,
                is_published=True,
            )

    response = client.get(
        reverse("catalog-sku-list"),
        {"category": "komplekty", "page_size": 20},
    )
    assert response.status_code == 200
    results = response.data["results"]
    assert response.data["count"] == 3
    assert len(results) == 3
    by_product = {row["product_slug"]: row["name"] for row in results}
    assert set(by_product) == {"h8101", "h8102", "h8103"}
    assert by_product["h8101"].startswith("H8101 |")
    assert "стандартная серия" in by_product["h8101"]
    assert "24A" not in by_product["h8101"]


@pytest.mark.django_db
def test_collapse_damu_samu_hva_hvd_one_card_per_product() -> None:
    """DAMU / SAMU / HVA / HVD Products collapse to one representative each."""
    cat_da = Category.objects.create(
        name="Без пружины",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    cat_sa = Category.objects.create(
        name="Дымоудаление",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya",
    )
    p_da = Product.objects.create(
        name="DA8MU | Электропривод воздушный без возвратной пружины, 8 Нм",
        slug="privod-vozdushniy-bez-pruzhini-damu-8nm",
        category=cat_da,
    )
    p_sa = Product.objects.create(
        name="SA10MU | Электропривод дымового клапана без возвратной пружины, 10 Нм",
        slug="privod-dimoudaleniya-10nm",
        category=cat_sa,
    )
    for code in ("DA8MU230-A", "DA8MU24-D", "DA8MU24-DS"):
        SKU.objects.create(
            product=p_da,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )
    for code in ("SA10MU230-DS", "SA10MU24-DS", "SA10MU24-DST"):
        SKU.objects.create(
            product=p_sa,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )
    p_hva = Product.objects.create(
        name="HVA 5 Нм",
        slug="privod-vozdushniy-hva-5nm",
        category=cat_da,
    )
    for code in ("HVA24-5", "HVA230-5"):
        SKU.objects.create(
            product=p_hva,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )
    p_hvd = Product.objects.create(
        name="HVD 3F",
        slug="privod-dimoudaleniya-hvd-3f",
        category=cat_sa,
    )
    for code in ("HVD24S-3F", "HVD230S-3F"):
        SKU.objects.create(
            product=p_hvd,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )
    p_hvd_air = Product.objects.create(
        name="HVD 5 Нм",
        slug="privod-vozdushniy-hvd-5nm",
        category=cat_da,
    )
    for code in ("HVD24-5", "HVD24S-5", "HVD230-5"):
        SKU.objects.create(
            product=p_hvd_air,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )

    qs = collapse_family_skus_for_list(SKU.objects.filter(is_published=True))
    codes = sorted(qs.values_list("sku_code", flat=True))
    assert codes == [
        "DA8MU230-A",
        "HVA230-5",
        "HVD230-5",
        "HVD230S-3F",
        "SA10MU230-DS",
    ]


@pytest.mark.django_db
def test_hvd_air_sibling_control_d_vs_ds() -> None:
    """HVD air editions expose D / DS on the variant picker."""
    from catalog.siblings import sibling_edition_row, variant_axes_from_siblings

    cat = Category.objects.create(
        name="Без пружины",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(
        name="HVD-5 | …",
        slug="privod-vozdushniy-hvd-5nm",
        category=cat,
    )
    rows = []
    for code in ("HVD24-5", "HVD24S-5", "HVD230-5"):
        sku = SKU.objects.create(
            product=product,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )
        rows.append(sibling_edition_row(sku))
    by_code = {r["sku_code"]: r["control"] for r in rows}
    assert by_code["HVD24-5"] == "D"
    assert by_code["HVD24S-5"] == "DS"
    assert by_code["HVD230-5"] == "D"
    axes = variant_axes_from_siblings(rows)
    assert axes["control"] == ["D", "DS"]
    assert set(axes["voltage"]) == {"24", "230"}


@pytest.mark.django_db
def test_collapse_prefers_in_stock_sku_else_first_of_series() -> None:
    """Family card: in-stock edition wins; if none/all out — min sku_code."""
    cat = Category.objects.create(
        name="Без пружины",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(
        name="DA8MU | …",
        slug="privod-vozdushniy-bez-pruzhini-damu-8nm",
        category=cat,
    )
    # Min code is out of stock; later AS is in stock → prefer AS.
    for code, qty in (
        ("DA8MU230-A", 0),
        ("DA8MU230-AS", 10),
        ("DA8MU24-D", 5),
    ):
        SKU.objects.create(
            product=product,
            name=code,
            slug=code.lower(),
            sku_code=code,
            stock_qty=qty,
            is_published=True,
        )

    qs = collapse_family_skus_for_list(SKU.objects.filter(is_published=True))
    assert list(qs.values_list("sku_code", flat=True)) == ["DA8MU230-AS"]

    # All out of stock → first of series (min code).
    SKU.objects.filter(product=product).update(stock_qty=0)
    qs_out = collapse_family_skus_for_list(SKU.objects.filter(is_published=True))
    assert list(qs_out.values_list("sku_code", flat=True)) == ["DA8MU230-A"]

    # All in stock → first of series among them (still min code).
    SKU.objects.filter(product=product).update(stock_qty=3)
    qs_all = collapse_family_skus_for_list(SKU.objects.filter(is_published=True))
    assert list(qs_all.values_list("sku_code", flat=True)) == ["DA8MU230-A"]


@pytest.mark.django_db
def test_collapse_safu_one_card_per_nm() -> None:
    """SAFU fire Products collapse to one representative SKU each."""
    cat = Category.objects.create(
        name="Противопожарные",
        slug="elektroprivody-protivopozharnye-i-dymovye",
    )
    product = Product.objects.create(
        name="SA3FU | Электропривод противопожарного клапана с пружинным возвратом, 3 Нм",
        slug="privod-protivopozharniy-3nm",
        category=cat,
    )
    for code in ("sa3fu230-ds", "sa3fu230-dst", "sa3fu24-ds", "sa3fu24-dst"):
        SKU.objects.create(
            product=product,
            name=f"{code} | edition",
            slug=f"privod-protivopozharniy-3nm-{code}",
            sku_code=code,
            is_published=True,
        )

    qs = collapse_family_skus_for_list(SKU.objects.filter(is_published=True))
    codes = list(qs.values_list("sku_code", flat=True))
    assert codes == ["sa3fu230-ds"]


@pytest.mark.django_db
def test_safu_list_shows_product_series_title(client: APIClient) -> None:
    """GET skus/?category=…protivopozharnye… collapses SAFU to Product.name."""
    cat = Category.objects.create(
        name="Противопожарные",
        slug="elektroprivody-protivopozharnye-i-dymovye",
    )
    product = Product.objects.create(
        name="SA3FU | Электропривод противопожарного клапана с пружинным возвратом, 3 Нм",
        slug="privod-protivopozharniy-3nm",
        category=cat,
    )
    for code in ("sa3fu230-ds", "sa3fu230-dst"):
        SKU.objects.create(
            product=product,
            name=f"{code} | Электропривод противопожарного клапана с пружинным возвратом",
            slug=f"privod-protivopozharniy-3nm-{code}",
            sku_code=code,
            is_published=True,
        )

    response = client.get(
        reverse("catalog-sku-list"),
        {
            "category": "elektroprivody-protivopozharnye-i-dymovye",
            "page_size": 20,
        },
    )
    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["product_slug"] == "privod-protivopozharniy-3nm"
    assert row["name"].startswith("SA3FU |")
    assert "230-ds" not in row["name"].casefold()


@pytest.mark.django_db
def test_samu_sibling_control_distinguishes_dst() -> None:
    """DST must not collapse into DS on the variant picker axis."""
    from catalog.siblings import sibling_edition_row, variant_axes_from_siblings

    cat = Category.objects.create(
        name="Дымоудаление",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya",
    )
    product = Product.objects.create(
        name="SA10MU | …",
        slug="privod-dimoudaleniya-10nm",
        category=cat,
    )
    rows = []
    for code in ("SA10MU24-DS", "SA10MU24-DST", "SA10MU230-DS"):
        sku = SKU.objects.create(
            product=product,
            name=code,
            slug=code.lower(),
            sku_code=code,
            is_published=True,
        )
        rows.append(sibling_edition_row(sku))
    by_code = {r["sku_code"]: r["control"] for r in rows}
    assert by_code["SA10MU24-DS"] == "DS"
    assert by_code["SA10MU24-DST"] == "DST"
    axes = variant_axes_from_siblings(rows)
    assert axes["control"] == ["DS", "DST"]
    assert set(axes["voltage"]) == {"24", "230"}


@pytest.mark.django_db
def test_list_edition_count_on_family_and_single(client: APIClient) -> None:
    """List cards expose published sibling count for family CTA signal."""
    cat = Category.objects.create(
        name="Без пружины edition-count",
        slug="elektroprivody-edition-count-test",
    )
    family = Product.objects.create(
        name="DA99MU | …",
        slug="privod-vozdushniy-bez-pruzhini-damu-99nm",
        category=cat,
    )
    for code in ("DA99MU24-A", "DA99MU24-D", "DA99MU230-A", "DA99MU230-D"):
        SKU.objects.create(
            product=family,
            name=code,
            slug=f"edition-count-{code.lower()}",
            sku_code=code,
            is_published=True,
        )
    alone_product = Product.objects.create(
        name="Одиночный",
        slug="privod-single-edition-count-test",
        category=cat,
    )
    SKU.objects.create(
        product=alone_product,
        name="SINGLE-EDCOUNT-1",
        slug="single-edcount-1",
        sku_code="SINGLE-EDCOUNT-1",
        is_published=True,
    )

    response = client.get(
        reverse("catalog-sku-list"),
        {
            "category": "elektroprivody-edition-count-test",
            "page_size": 50,
        },
    )
    assert response.status_code == 200
    by_product = {row["product_slug"]: row for row in response.data["results"]}
    assert by_product["privod-vozdushniy-bez-pruzhini-damu-99nm"]["edition_count"] == 4
    assert by_product["privod-single-edition-count-test"]["edition_count"] == 1


@pytest.mark.django_db
def test_damu_list_shows_product_series_title(client: APIClient) -> None:
    """GET skus/?category=…bez-pruzhinnogo… collapses DAMU to Product.name."""
    cat = Category.objects.create(
        name="Без пружины",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(
        name="DA4MU | Электропривод воздушный без возвратной пружины, 4 Нм",
        slug="privod-vozdushniy-bez-pruzhini-damu-4nm",
        category=cat,
    )
    for code in ("DA4MU24-A", "DA4MU24-D", "DA4MU230-AS"):
        SKU.objects.create(
            product=product,
            name=f"{code} | edition",
            slug=f"privod-vozdushniy-bez-pruzhini-damu-4nm-{code.lower()}",
            sku_code=code,
            is_published=True,
        )

    response = client.get(
        reverse("catalog-sku-list"),
        {
            "category": "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
            "page_size": 20,
        },
    )
    assert response.status_code == 200
    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["product_slug"] == "privod-vozdushniy-bez-pruzhini-damu-4nm"
    assert row["name"].startswith("DA4MU |")
    assert "24-A" not in row["name"]
