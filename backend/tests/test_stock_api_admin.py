"""API + Admin coverage for SKU stock / in_stock."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

User = get_user_model()


def _xlsx_upload(rows: list[list[object]], name: str = "stock.xlsx") -> SimpleUploadedFile:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buf = BytesIO()
    book.save(buf)
    return SimpleUploadedFile(
        name,
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@pytest.mark.django_db
def test_sku_list_exposes_in_stock_not_qty(client) -> None:
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Cat", slug="stock-api-cat")
    product = Product.objects.create(name="P", slug="stock-api-p", category=cat)
    SKU.objects.create(
        product=product,
        name="In",
        slug="stock-api-in",
        sku_code="STK-IN",
        stock_qty=2,
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        name="Out",
        slug="stock-api-out",
        sku_code="STK-OUT",
        stock_qty=0,
        is_published=True,
    )

    response = client.get(reverse("catalog-sku-list"))
    assert response.status_code == 200
    by_code = {row["sku_code"]: row for row in response.data["results"]}
    assert by_code["STK-IN"]["in_stock"] is True
    assert by_code["STK-OUT"]["in_stock"] is False
    assert "stock_qty" not in by_code["STK-IN"]
    assert "stock_qty" not in by_code["STK-OUT"]


@pytest.mark.django_db
def test_sku_list_filter_in_stock_only(client) -> None:
    """``?in_stock=1`` returns only SKUs with stock_qty > 0."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Cat", slug="stock-filter-cat")
    product = Product.objects.create(name="P", slug="stock-filter-p", category=cat)
    SKU.objects.create(
        product=product,
        name="In",
        slug="stock-filter-in",
        sku_code="FLT-IN",
        stock_qty=5,
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        name="Out",
        slug="stock-filter-out",
        sku_code="FLT-OUT",
        stock_qty=0,
        is_published=True,
    )

    response = client.get(reverse("catalog-sku-list"), {"in_stock": "1"})
    assert response.status_code == 200
    codes = {row["sku_code"] for row in response.data["results"]}
    assert "FLT-IN" in codes
    assert "FLT-OUT" not in codes


@pytest.mark.django_db
def test_stock_upload_admin_requires_staff(client) -> None:
    url = reverse("admin:catalog_sku_import_stock")
    assert client.get(url).status_code in {302, 403}


@pytest.mark.django_db
def test_stock_upload_admin_page_has_unfold_actions(client) -> None:
    admin = User.objects.create_superuser(
        username="stock-ui",
        email="stock-ui@example.com",
        password="x",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:catalog_sku_import_stock"))
    assert response.status_code == 200
    html = response.content.decode()
    assert 'type="submit"' in html
    assert "Загрузить остатки" in html
    assert "Выберите файл" in html or "file_upload" in html
    assert 'enctype="multipart/form-data"' in html


@pytest.mark.django_db
def test_stock_upload_admin_applies_xlsx(client) -> None:
    from catalog.models import SKU, Category, Product

    admin = User.objects.create_superuser(
        username="stock-admin",
        email="stock@example.com",
        password="x",
    )
    cat = Category.objects.create(name="Cat2", slug="stock-adm-cat")
    product = Product.objects.create(name="P2", slug="stock-adm-p", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="stock-adm-s",
        sku_code="ADM-1",
        stock_qty=0,
    )

    client.force_login(admin)
    upload = _xlsx_upload([["Артикул", "Остатки"], ["ADM-1", 5], ["GHOST", 9]])
    response = client.post(
        reverse("admin:catalog_sku_import_stock"),
        {"file": upload},
    )
    assert response.status_code == 302
    sku.refresh_from_db()
    assert sku.stock_qty == 5
    assert sku.in_stock is True


@pytest.mark.django_db
def test_stock_template_download(client) -> None:
    admin = User.objects.create_superuser(
        username="stock-tpl",
        email="tpl@example.com",
        password="x",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:catalog_sku_stock_template"))
    assert response.status_code == 200
    assert "spreadsheetml" in response["Content-Type"]
    assert response.content[:2] == b"PK"
