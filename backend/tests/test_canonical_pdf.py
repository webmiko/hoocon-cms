"""One public PDF URL per document. Copies on cards must not each be a URL.

The hash is sha256 of ``kind + newline + normalized title``, first 10 hex
digits. Kind comes from the title (``Инструкция`` → manual, ``Паспорт`` →
passport) or, failing that, from file_type (certificate / catalog).
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse


def _digest(kind: str, title: str) -> str:
    """Independent hash of the documented canonical-path contract."""
    normalized = " ".join(title.split()).casefold()
    return hashlib.sha256(f"{kind}\n{normalized}".encode()).hexdigest()[:10]


def _path(url: str) -> str:
    return urlparse(url).path


def _pdf_body(response) -> bytes:
    return b"".join(response.streaming_content)


def _family(prefix: str):
    """Two published SKUs in one DA family, plus a helper SKU factory."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="DAMU pdf", slug=f"damu-pdf-{prefix}")
    product = Product.objects.create(
        name="DA2MU",
        slug=f"da2mu-pdf-{prefix}",
        category=cat,
    )
    sku_a = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-D",
        name="DA2MU24-D",
        slug=f"da2mu24-d-pdf-{prefix}",
        is_published=True,
    )
    sku_b = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-DS",
        name="DA2MU24-DS",
        slug=f"da2mu24-ds-pdf-{prefix}",
        is_published=True,
    )
    return sku_a, sku_b


def _attach(sku, title: str, body: bytes, *, file_type: str):
    from catalog.models import ProductFile

    row = ProductFile(
        sku=sku,
        title=title,
        file_type=file_type,
        is_published=True,
        sort_order=0,
    )
    row.file.save("doc.pdf", ContentFile(body), save=True)
    return row


@pytest.mark.django_db
def test_shared_manual_has_one_url_and_the_card_links_to_it(client) -> None:
    """Two editions of one series share a manual. Both cards and the HTML point at it."""
    from catalog.models import ProductFile
    from catalog.urls_paths import catalog_path_for_sku

    sku_a, sku_b = _family("shared")
    title = "Инструкция DA2MU (D/DS)"
    _attach(sku_a, title, b"%PDF-shared-a", file_type=ProductFile.FileType.DATASHEET)
    _attach(sku_b, title, b"%PDF-shared-b", file_type=ProductFile.FileType.DATASHEET)
    _attach(
        sku_a,
        "Паспорт DA2MU24-D",
        b"%PDF-pass-a",
        file_type=ProductFile.FileType.DATASHEET,
    )

    detail_a = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_a.slug}))
    detail_b = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_b.slug}))
    assert detail_a.status_code == 200
    assert detail_b.status_code == 200
    url_a = next(row["file"] for row in detail_a.json()["files"] if row["title"] == title)
    url_b = next(row["file"] for row in detail_b.json()["files"] if row["title"] == title)
    assert _path(url_a) == _path(url_b)
    path = _path(url_a)
    digest = _digest("manual", title)
    assert path.startswith("/dokumentaciya/pdf/da2mu/instrukciya-")
    assert digest in path
    assert "/media/" not in url_a

    listed = client.get(reverse("catalog-sku-file-list", kwargs={"sku_slug": sku_b.slug}))
    assert listed.status_code == 200
    listed_manual = next(row["file"] for row in listed.json()["results"] if row["title"] == title)
    assert _path(listed_manual) == path

    downloaded = client.get(path)
    assert downloaded.status_code == 200
    assert downloaded["Content-Type"].startswith("application/pdf")
    assert downloaded["Content-Disposition"].startswith("inline;")
    assert "X-Robots-Tag" not in downloaded
    assert _pdf_body(downloaded) == b"%PDF-shared-a"

    page = client.get(catalog_path_for_sku(sku_a))
    assert page.status_code == 200
    assert f'href="{path}"' in page.content.decode()

    hub = client.get(reverse("catalog-docs"), {"q": "DA2MU (D/DS)"})
    hub_urls = [_path(row["file"]) for row in hub.json()["files"] if row["title"] == title]
    assert hub_urls == [path]

    sitemap = client.get("/sitemap.xml").content.decode()
    assert sitemap.count(path) == 1
    assert "/media/product_files/" not in sitemap


@pytest.mark.django_db
def test_hiding_the_first_copy_serves_the_next_one(client) -> None:
    """The public URL stays. Hiding the winning card promotes the other copy."""
    from catalog.models import ProductFile

    sku_a, sku_b = _family("promote")
    title = "Инструкция DA2MU (D/DS)"
    _attach(sku_a, title, b"%PDF-first", file_type=ProductFile.FileType.DATASHEET)
    _attach(sku_b, title, b"%PDF-second", file_type=ProductFile.FileType.DATASHEET)
    detail = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_a.slug}))
    path = _path(detail.json()["files"][0]["file"])
    assert _pdf_body(client.get(path)) == b"%PDF-first"

    sku_a.is_published = False
    sku_a.save(update_fields=["is_published"])
    promoted = client.get(path)
    assert promoted.status_code == 200
    assert _pdf_body(promoted) == b"%PDF-second"


@pytest.mark.django_db
def test_a_manual_with_the_same_title_in_another_family_stays_separate(client) -> None:
    """DA and SA instructions are different documents even when the title matches."""
    from catalog.models import SKU, Category, Product, ProductFile

    sku_da, _sku_ds = _family("split")
    cat = Category.objects.create(name="SAMU pdf", slug="samu-pdf-split")
    product = Product.objects.create(name="SA10FU", slug="sa10fu-pdf-split", category=cat)
    sku_sa = SKU.objects.create(
        product=product,
        sku_code="SA10FU24-D",
        name="SA10FU24-D",
        slug="sa10fu24-d-pdf-split",
        is_published=True,
    )
    title = "Инструкция серии"
    _attach(sku_da, title, b"%PDF-da", file_type=ProductFile.FileType.DATASHEET)
    _attach(sku_sa, title, b"%PDF-sa", file_type=ProductFile.FileType.DATASHEET)

    da = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_da.slug}))
    sa = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_sa.slug}))
    path_da = _path(da.json()["files"][0]["file"])
    path_sa = _path(sa.json()["files"][0]["file"])
    assert path_da.startswith("/dokumentaciya/pdf/da2mu/")
    assert path_sa.startswith("/dokumentaciya/pdf/sa10fu/")
    assert path_da != path_sa
    assert _pdf_body(client.get(path_da)) == b"%PDF-da"
    assert _pdf_body(client.get(path_sa)) == b"%PDF-sa"


@pytest.mark.django_db
def test_one_certificate_url_for_every_family(client) -> None:
    """A certificate attached to many cards is a single URL, not one per family."""
    from catalog.models import SKU, Category, Product, ProductFile

    sku_da, _sku_ds = _family("cert")
    cat = Category.objects.create(name="SAMU cert", slug="samu-pdf-cert")
    product = Product.objects.create(name="SA10FU", slug="sa10fu-pdf-cert", category=cat)
    sku_sa = SKU.objects.create(
        product=product,
        sku_code="SA10FU24-D",
        name="SA10FU24-D",
        slug="sa10fu24-d-pdf-cert",
        is_published=True,
    )
    title = "Сертификат EAC ROSS"
    _attach(sku_da, title, b"%PDF-cert-a", file_type=ProductFile.FileType.CERTIFICATE)
    _attach(sku_sa, title, b"%PDF-cert-b", file_type=ProductFile.FileType.CERTIFICATE)

    da = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_da.slug}))
    sa = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_sa.slug}))
    path_da = _path(da.json()["files"][0]["file"])
    path_sa = _path(sa.json()["files"][0]["file"])
    assert path_da == path_sa
    assert path_da.startswith("/dokumentaciya/pdf/obshchee/sertifikat-")
    assert _digest("certificate", title) in path_da
    assert _pdf_body(client.get(path_da)) == b"%PDF-cert-a"


@pytest.mark.django_db
def test_unknown_and_hidden_pdf_are_not_served(client) -> None:
    """A guessed stem is 404. A file on a hidden card is not that URL."""
    from catalog.models import ProductFile

    missing = client.get("/dokumentaciya/pdf/da2mu/instrukciya-net-0123456789.pdf")
    assert missing.status_code == 404
    assert b"%PDF" not in missing.content

    sku_a, _sku_b = _family("hidden")
    row_title = "Паспорт DA2MU24-D"
    _attach(sku_a, row_title, b"%PDF-hidden", file_type=ProductFile.FileType.DATASHEET)
    detail = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku_a.slug}))
    path = _path(detail.json()["files"][0]["file"])
    assert _digest("passport", row_title) in path
    sku_a.is_published = False
    sku_a.save(update_fields=["is_published"])
    assert client.get(path).status_code == 404


def test_robots_does_not_block_pdf_fetch(client) -> None:
    """noindex on storage copies needs a fetch. robots.txt must not Disallow them."""
    body = client.get("/robots.txt").content.decode()
    assert "product_files" not in body
    assert "dokumentaciya/pdf" not in body
