"""SEO and catalog search must not publish an unconfirmed Belimo code.

The card already shows only an active Belimo AnalogMap. Title, description,
crawler text, llms.txt and ?q= used to read SKU.analog_belimo_code, so a
stale cache (HVA24-5QX → LMQ24A-SR while AnalogMap stores EF24A-SR) was
indexed. Expected articles below are the ones written into AnalogMap in
this test, not a value copied from the page.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

STALE = "LMQ24A-SR"
CONFIRMED = "EF24A-SR"
UNCONFIRMED = "NF24A-SR"


def _sku(sku_code: str, slug: str, *, analog: str):
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздух", slug=f"vozduh-{slug}")
    product = Product.objects.create(name=sku_code, slug=f"prod-{slug}", category=cat)
    return SKU.objects.create(
        product=product,
        name=sku_code,
        slug=slug,
        sku_code=sku_code,
        analog_belimo_code=analog,
        is_published=True,
    )


@pytest.mark.django_db
def test_seo_publishes_confirmed_belimo_article_not_stale_field(client) -> None:
    """A different stored code must not appear in title, description, crawl or llms."""
    from catalog.models import AnalogMap
    from catalog.urls_paths import catalog_path_for_sku

    sku = _sku("HVA24-5QX", "hva24-5qx-seo", analog=STALE)
    AnalogMap.objects.create(brand="Belimo", foreign_code=CONFIRMED, sku=sku, torque_nm=5, is_active=True)
    bare = _sku("DA15FU24-A", "da15fu24-a-seo", analog=UNCONFIRMED)

    page = client.get(catalog_path_for_sku(sku))
    assert page.status_code == 200
    html = page.content.decode()
    assert f"аналог {CONFIRMED}" in html
    assert f"Аналог Belimo {CONFIRMED}" in html
    assert f"Аналог Belimo: {CONFIRMED}" in html
    assert STALE not in html

    bare_page = client.get(catalog_path_for_sku(bare))
    assert bare_page.status_code == 200
    bare_html = bare_page.content.decode()
    assert UNCONFIRMED not in bare_html
    assert "Аналог Belimo" not in bare_html

    for path in ("/llms.txt", "/llms-full.txt"):
        body = client.get(path).content.decode()
        assert CONFIRMED in body
        assert "HVA24-5QX" in body
        assert STALE not in body
        assert UNCONFIRMED not in body


@pytest.mark.django_db
def test_inactive_belimo_map_is_not_published(client) -> None:
    """An inactive row is not a confirmed pair, even when the stored field matches it."""
    from catalog.models import AnalogMap
    from catalog.urls_paths import catalog_path_for_sku

    sku = _sku("HVD24-10", "hvd24-10-seo", analog="GM24A")
    AnalogMap.objects.create(brand="Belimo", foreign_code="GM24A", sku=sku, is_active=False)

    html = client.get(catalog_path_for_sku(sku)).content.decode()
    assert "GM24A" not in html
    assert "GM24A" not in client.get("/llms.txt").content.decode()


@pytest.mark.django_db
def test_catalog_search_matches_confirmed_belimo_article_only(client) -> None:
    """?q= finds the AnalogMap article and ignores the stale stored code."""
    from catalog.models import AnalogMap

    sku = _sku("HVA24-5QX", "hva24-5qx-search", analog=STALE)
    AnalogMap.objects.create(brand="Belimo", foreign_code=CONFIRMED, sku=sku, is_active=True)
    _sku("DA15FU24-A", "da15fu24-a-search", analog=UNCONFIRMED)

    stale = client.get(reverse("catalog-sku-list"), {"q": STALE})
    assert stale.status_code == 200
    assert stale.data["results"] == []

    unconfirmed = client.get(reverse("catalog-sku-list"), {"q": UNCONFIRMED})
    assert unconfirmed.data["results"] == []

    confirmed = client.get(reverse("catalog-sku-list"), {"q": CONFIRMED})
    assert [row["sku_code"] for row in confirmed.data["results"]] == ["HVA24-5QX"]
