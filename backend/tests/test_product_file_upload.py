"""Tests for ProductFile upload endpoint (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 2 — upload view + валидация (модель уже в catalog с Iter 1);
docs/security-baseline.md §1 (PDF: allowlist MIME, size, no path traversal);
docs/data-quality-etl.md §4.3.

Endpoint: POST /api/catalog/skus/{slug}/files/ (staff only).
Public read: GET (already covered by SKU detail in Slice 9).
"""

from __future__ import annotations

from io import BytesIO

import pytest
from django.urls import reverse


def _pdf_bytes(size: int = 128) -> bytes:
    """Minimal PDF magic header padded to `size` bytes."""
    body = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    if size <= len(body):
        return body[:size]
    return body + b"0" * (size - len(body))


def _make_sku():
    """Helper: Category → Product → SKU for upload target."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-up")
    product = Product.objects.create(name="HVA", slug="hva-up", category=cat)
    return SKU.objects.create(
        product=product,
        name="HVA 5NM",
        slug="hva-5nm-up",
        sku_code="HVA-5NM-UP",
        is_published=True,
    )


def _staff_user(django_user_model):
    """Create a staff user for authenticated uploads."""
    return django_user_model.objects.create_user(
        username="uploader",
        password="test-pass-not-secret",
        is_staff=True,
    )


# ── AuthN / AuthZ ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_upload_anon_forbidden(client) -> None:
    """Anonymous user cannot upload files (403)."""
    sku = _make_sku()
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    response = client.post(
        url,
        {"title": "T", "file": BytesIO(_pdf_bytes()), "file_type": "datasheet"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_upload_non_staff_forbidden(client, django_user_model) -> None:
    """Authenticated non-staff user cannot upload (403)."""
    sku = _make_sku()
    user = django_user_model.objects.create_user(
        username="regular",
        password="test-pass-not-secret",
        is_staff=False,
    )
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    response = client.post(
        url,
        {"title": "T", "file": BytesIO(_pdf_bytes()), "file_type": "datasheet"},
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_upload_staff_accepted(client, django_user_model) -> None:
    """Staff user can upload a valid PDF (201)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    sku = _make_sku()
    user = _staff_user(django_user_model)
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    uploaded = SimpleUploadedFile(
        "datasheet.pdf",
        _pdf_bytes(256),
        content_type="application/pdf",
    )
    response = client.post(
        url,
        {"title": "Паспорт", "file": uploaded, "file_type": "datasheet"},
        format="multipart",
    )
    assert response.status_code == 201, response.content
    from catalog.models import ProductFile

    assert ProductFile.objects.filter(sku=sku).count() == 1


# ── Validation: reject bad files ────────────────────────────────────


@pytest.mark.django_db
def test_upload_rejects_exe_extension(client, django_user_model) -> None:
    """Upload with .exe extension is rejected (400)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    sku = _make_sku()
    user = _staff_user(django_user_model)
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    uploaded = SimpleUploadedFile(
        "malware.exe",
        _pdf_bytes(256),  # valid PDF bytes but wrong extension
        content_type="application/pdf",
    )
    response = client.post(
        url,
        {"title": "T", "file": uploaded, "file_type": "datasheet"},
        format="multipart",
    )
    assert response.status_code == 400
    from catalog.models import ProductFile

    assert ProductFile.objects.filter(sku=sku).count() == 0


@pytest.mark.django_db
def test_upload_path_traversal_filename_sanitized(client, django_user_model) -> None:
    """Filename with '../' is sanitized by Django + our upload_to (UUID).

    Django's SimpleUploadedFile strips directory components before our
    validator sees them; our product_file_upload_to adds a UUID prefix.
    The security property: the stored file path contains no '..' or
    directory traversal, even if the client sends a malicious name.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    sku = _make_sku()
    user = _staff_user(django_user_model)
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    uploaded = SimpleUploadedFile(
        "../etc/passwd.pdf",
        _pdf_bytes(128),
        content_type="application/pdf",
    )
    response = client.post(
        url,
        {"title": "T", "file": uploaded, "file_type": "datasheet"},
        format="multipart",
    )
    # Django strips the path → upload succeeds (201); the stored path is safe.
    assert response.status_code == 201, response.content
    from catalog.models import ProductFile

    pf = ProductFile.objects.get(sku=sku)
    stored_path = pf.file.name
    assert ".." not in stored_path, f"traversal in stored path: {stored_path}"
    assert "/" not in stored_path.split("product_files/")[1].split("/")[0], (
        f"unexpected dir in stored path: {stored_path}"
    )
    # The basename should be passwd.pdf (Django-stripped) with a UUID prefix.
    assert stored_path.endswith("passwd.pdf")


@pytest.mark.django_db
def test_upload_rejects_bad_magic_bytes(client, django_user_model) -> None:
    """Upload with non-PDF magic bytes is rejected (400)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    sku = _make_sku()
    user = _staff_user(django_user_model)
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    uploaded = SimpleUploadedFile(
        "fake.pdf",
        b"MZ\x90\x00not-a-pdf",
        content_type="application/pdf",
    )
    response = client.post(
        url,
        {"title": "T", "file": uploaded, "file_type": "datasheet"},
        format="multipart",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_upload_rejects_wrong_mime(client, django_user_model) -> None:
    """Upload with non-PDF MIME is rejected (400)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    sku = _make_sku()
    user = _staff_user(django_user_model)
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    uploaded = SimpleUploadedFile(
        "ok.pdf",
        _pdf_bytes(128),
        content_type="application/x-msdownload",
    )
    response = client.post(
        url,
        {"title": "T", "file": uploaded, "file_type": "datasheet"},
        format="multipart",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_upload_rejects_empty_file(client, django_user_model) -> None:
    """Zero-byte upload is rejected (400)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    sku = _make_sku()
    user = _staff_user(django_user_model)
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    uploaded = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
    response = client.post(
        url,
        {"title": "T", "file": uploaded, "file_type": "datasheet"},
        format="multipart",
    )
    assert response.status_code == 400


# ── 404 on unknown SKU ──────────────────────────────────────────────


@pytest.mark.django_db
def test_upload_to_unknown_sku_returns_404(client, django_user_model) -> None:
    """Upload to a non-existent SKU slug returns 404."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    user = _staff_user(django_user_model)
    client.force_login(user)
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": "no-such-sku"})
    uploaded = SimpleUploadedFile(
        "d.pdf",
        _pdf_bytes(128),
        content_type="application/pdf",
    )
    response = client.post(
        url,
        {"title": "T", "file": uploaded, "file_type": "datasheet"},
        format="multipart",
    )
    assert response.status_code == 404


# ── List uploaded files ─────────────────────────────────────────────


@pytest.mark.django_db
def test_list_files_for_sku(client) -> None:
    """GET returns published ProductFile metadata for a SKU."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from catalog.models import ProductFile

    sku = _make_sku()
    ProductFile.objects.create(
        sku=sku,
        title="Паспорт",
        file=SimpleUploadedFile("d.pdf", _pdf_bytes(64), content_type="application/pdf"),
        file_type=ProductFile.FileType.DATASHEET,
    )
    url = reverse("catalog-sku-file-list", kwargs={"sku_slug": sku.slug})
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["title"] == "Паспорт"
