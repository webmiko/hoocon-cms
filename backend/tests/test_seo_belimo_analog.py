"""SEO and catalog search use the manually stored ``SKU.analog_belimo_code``."""

from __future__ import annotations

import pytest
from django.urls import reverse

CONFIRMED = "EF24A-SR"
EMPTY = ""


def _sku(sku_code: str, slug: str, *, analog: str):
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздух", slug=f"vozduh-{slug}")
    product = Product.objects.create(name=sku_code, slug=f"prod-{slug}", category=cat)
    return SKU.objects.create(
        product=product,
        name=sku_code,
        slug=slug,
        sku_code=sku_code,
        analog_belimo_code=analog or None,
        is_published=True,
    )


@pytest.mark.django_db
def test_seo_pdp_hides_belimo_outside_analogs_tab(client) -> None:
    """PDP title/crawl omit Belimo; llms index still lists manual pairs."""
    from catalog.urls_paths import catalog_path_for_sku

    sku = _sku("HVA24-5QX", "hva24-5qx-seo", analog=CONFIRMED)
    _sku("DA15FU24-A", "da15fu24-a-seo", analog=EMPTY)

    page = client.get(catalog_path_for_sku(sku))
    assert page.status_code == 200
    html = page.content.decode()
    assert f"аналог {CONFIRMED}" not in html.lower()
    assert "Аналог Belimo" not in html

    for path in ("/llms.txt", "/llms-full.txt"):
        body = client.get(path).content.decode()
        assert CONFIRMED in body
        assert "HVA24-5QX" in body
        assert f"{CONFIRMED} → HVA24-5QX" in body


@pytest.mark.django_db
def test_catalog_search_matches_manual_belimo_code(client) -> None:
    """?q= finds SKUs by stored Belimo article."""
    _sku("HVA24-5QX", "hva24-5qx-search", analog=CONFIRMED)
    _sku("DA15FU24-A", "da15fu24-a-search", analog=EMPTY)

    confirmed = client.get(reverse("catalog-sku-list"), {"q": CONFIRMED})
    assert [row["sku_code"] for row in confirmed.data["results"]] == ["HVA24-5QX"]

    miss = client.get(reverse("catalog-sku-list"), {"q": "LMQ24A-SR"})
    assert miss.data["results"] == []
