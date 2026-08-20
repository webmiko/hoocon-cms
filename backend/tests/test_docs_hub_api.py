"""API tests for documentation hub list + family zip."""

from __future__ import annotations

import io
import zipfile

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse


def _seed_docs_family():
    """Two SKUs sharing one instruction + one passport each."""
    from catalog.models import SKU, Category, Product, ProductFile

    cat = Category.objects.create(name="DAMU hub", slug="damu-hub-api")
    product = Product.objects.create(
        name="DA2MU",
        slug="privod-vozdushniy-bez-pruzhini-damu-2nm-hub",
        category=cat,
    )
    sku_a = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-D",
        name="DA2MU24-D",
        slug="da2mu24-d-hub",
        is_published=True,
    )
    sku_b = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-DS",
        name="DA2MU24-DS",
        slug="da2mu24-ds-hub",
        is_published=True,
    )
    title = "Инструкция DA2MU (D/DS)"
    for sku, body in ((sku_a, b"%PDF-shared-a"), (sku_b, b"%PDF-shared-b")):
        pf = ProductFile(
            sku=sku,
            title=title,
            file_type=ProductFile.FileType.DATASHEET,
            is_published=True,
            sort_order=0,
        )
        pf.file.save(f"{sku.slug}-manual.pdf", ContentFile(body), save=True)
    for sku, body in (
        (sku_a, b"%PDF-pass-a"),
        (sku_b, b"%PDF-pass-b"),
    ):
        pf = ProductFile(
            sku=sku,
            title=f"Паспорт {sku.sku_code}",
            file_type=ProductFile.FileType.DATASHEET,
            is_published=True,
            sort_order=1,
        )
        pf.file.save(f"{sku.slug}-pass.pdf", ContentFile(body), save=True)
    return sku_a, sku_b


@pytest.mark.django_db
def test_docs_hub_list_dedupes_manuals(client) -> None:
    _seed_docs_family()
    response = client.get(reverse("catalog-docs"))
    assert response.status_code == 200
    data = response.json()
    titles = [f["title"] for f in data["files"]]
    assert titles.count("Инструкция DA2MU (D/DS)") == 1
    assert "Паспорт DA2MU24-D" in titles
    assert "Паспорт DA2MU24-DS" in titles
    families = {f["key"]: f for f in data["families"]}
    assert families["DA2MU"]["file_count"] == 3
    assert families["DA2MU"]["series"] == "DA"
    assert families["DA2MU"]["zip_path"].endswith("/DA2MU/zip/")


@pytest.mark.django_db
def test_docs_hub_list_filters(client) -> None:
    _seed_docs_family()
    by_kind = client.get(reverse("catalog-docs"), {"kind": "passport"})
    assert by_kind.status_code == 200
    assert all(f["kind"] == "passport" for f in by_kind.json()["files"])
    assert len(by_kind.json()["files"]) == 2

    by_q = client.get(reverse("catalog-docs"), {"q": "DA2MU24-DS"})
    assert by_q.status_code == 200
    titles = [f["title"] for f in by_q.json()["files"]]
    assert "Паспорт DA2MU24-DS" in titles

    by_series = client.get(reverse("catalog-docs"), {"series": "SA"})
    assert by_series.status_code == 200
    assert by_series.json()["files"] == []


@pytest.mark.django_db
def test_docs_family_zip_unique_and_etag(client) -> None:
    _seed_docs_family()
    url = reverse("catalog-docs-family-zip", kwargs={"key": "DA2MU"})
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "DA2MU-docs.zip" in response["Content-Disposition"]
    etag = response["ETag"].strip('"')
    assert etag

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = zf.namelist()
    assert len(names) == 3

    cached = client.get(url, HTTP_IF_NONE_MATCH=f'"{etag}"')
    assert cached.status_code == 304


@pytest.mark.django_db
def test_docs_family_zip_404(client) -> None:
    response = client.get(
        reverse("catalog-docs-family-zip", kwargs={"key": "NOSUCH"}),
    )
    assert response.status_code == 404
