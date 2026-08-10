"""Tests for catalog.ProductFile + PDF upload validators (TDD).

Spec: ПЛАН §6 Iter 1 (модель) / Iter 2 (upload checks); docs/security-baseline.md
§1 (PDF: allowlist MIME, size, no path traversal); docs/data-quality-etl.md §4.3;
docs/market-analysis.md §6 (type=certificate); БЗ Инъекции-и-валидация-ввода.md
(File Upload: MIME + extension + magic bytes; UUID-имя).

ProductFile = PDF/сертификат на SKU (download center на PDP).
Валидаторы — чистые функции: переиспользуются Admin/API/ETL.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError

# ── sanitize_upload_filename (path traversal) ──────────────────────


def test_sanitize_upload_filename_keeps_basename() -> None:
    """Plain basename is returned unchanged (lowercased extension preserved)."""
    from catalog.validators import sanitize_upload_filename

    assert sanitize_upload_filename("datasheet-hva-5nm.pdf") == "datasheet-hva-5nm.pdf"


def test_sanitize_upload_filename_strips_directory_components() -> None:
    """Path prefixes are stripped — only the final basename remains."""
    from catalog.validators import sanitize_upload_filename

    assert sanitize_upload_filename("foo/bar/datasheet.pdf") == "datasheet.pdf"
    assert sanitize_upload_filename("foo\\bar\\datasheet.pdf") == "datasheet.pdf"


def test_sanitize_upload_filename_rejects_dotdot() -> None:
    """Path segments with '..' or encoded slash are rejected."""
    from catalog.validators import sanitize_upload_filename

    with pytest.raises(ValidationError):
        sanitize_upload_filename("../etc/passwd.pdf")
    with pytest.raises(ValidationError):
        sanitize_upload_filename("foo/../../secret.pdf")
    with pytest.raises(ValidationError):
        sanitize_upload_filename("..")
    with pytest.raises(ValidationError):
        sanitize_upload_filename("..%2Fsecret.pdf")


def test_sanitize_upload_filename_rejects_null_byte() -> None:
    """Null byte in filename is rejected (classic upload bypass)."""
    from catalog.validators import sanitize_upload_filename

    with pytest.raises(ValidationError):
        sanitize_upload_filename("safe.pdf\x00.exe")


def test_sanitize_upload_filename_rejects_empty() -> None:
    """Empty / whitespace-only name is rejected."""
    from catalog.validators import sanitize_upload_filename

    with pytest.raises(ValidationError):
        sanitize_upload_filename("")
    with pytest.raises(ValidationError):
        sanitize_upload_filename("   ")


# ── validate_pdf_upload (MIME / size / magic) ──────────────────────


def _pdf_bytes(size: int = 64) -> bytes:
    """Minimal PDF magic header padded to `size` bytes."""
    body = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    if size <= len(body):
        return body[:size]
    return body + b"0" * (size - len(body))


def test_validate_pdf_upload_accepts_valid_pdf() -> None:
    """Valid PDF (extension + magic + size) passes without error."""
    from catalog.validators import validate_pdf_upload

    uploaded = SimpleUploadedFile(
        "ok.pdf",
        _pdf_bytes(128),
        content_type="application/pdf",
    )
    validate_pdf_upload(uploaded)  # no raise


def test_validate_pdf_upload_rejects_wrong_extension() -> None:
    """Non-.pdf extension is rejected even with PDF MIME."""
    from catalog.validators import validate_pdf_upload

    uploaded = SimpleUploadedFile(
        "malware.exe",
        _pdf_bytes(128),
        content_type="application/pdf",
    )
    with pytest.raises(ValidationError):
        validate_pdf_upload(uploaded)


def test_validate_pdf_upload_rejects_wrong_mime() -> None:
    """Non-PDF MIME is rejected."""
    from catalog.validators import validate_pdf_upload

    uploaded = SimpleUploadedFile(
        "ok.pdf",
        _pdf_bytes(128),
        content_type="application/x-msdownload",
    )
    with pytest.raises(ValidationError):
        validate_pdf_upload(uploaded)


def test_validate_pdf_upload_rejects_bad_magic_bytes() -> None:
    """File without %PDF magic is rejected (MIME spoof)."""
    from catalog.validators import validate_pdf_upload

    uploaded = SimpleUploadedFile(
        "fake.pdf",
        b"MZ\x90\x00not-a-pdf",
        content_type="application/pdf",
    )
    with pytest.raises(ValidationError):
        validate_pdf_upload(uploaded)


def test_validate_pdf_upload_rejects_oversized() -> None:
    """File larger than MAX_PRODUCT_FILE_SIZE_BYTES is rejected."""
    from catalog.validators import MAX_PRODUCT_FILE_SIZE_BYTES, validate_pdf_upload

    oversized = SimpleUploadedFile(
        "huge.pdf",
        _pdf_bytes(MAX_PRODUCT_FILE_SIZE_BYTES + 1),
        content_type="application/pdf",
    )
    with pytest.raises(ValidationError):
        validate_pdf_upload(oversized)


def test_validate_pdf_upload_rejects_empty() -> None:
    """Zero-byte upload is rejected (ETL: size > 0)."""
    from catalog.validators import validate_pdf_upload

    empty = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
    with pytest.raises(ValidationError):
        validate_pdf_upload(empty)


# ── ProductFile model ─────────────────────────────────────────────


def _make_sku():
    """Helper: Category → Product → SKU for ProductFile FK tests."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-pf")
    product = Product.objects.create(name="HVA", slug="hva-pf", category=cat)
    return SKU.objects.create(
        product=product,
        name="HVA 5NM",
        slug="hva-5nm-pf",
        sku_code="HVA-5NM-PF",
    )


@pytest.mark.django_db
def test_create_product_file_for_sku() -> None:
    """Can attach a ProductFile (PDF datasheet) to a SKU."""
    from catalog.models import ProductFile

    sku = _make_sku()
    uploaded = SimpleUploadedFile(
        "datasheet.pdf",
        _pdf_bytes(256),
        content_type="application/pdf",
    )
    pf = ProductFile.objects.create(
        sku=sku,
        title="Паспорт HVA-5NM",
        file=uploaded,
        file_type=ProductFile.FileType.DATASHEET,
    )
    assert pf.pk is not None
    assert pf.sku_id == sku.pk
    assert pf.file_type == "datasheet"
    assert pf.is_published is True


@pytest.mark.django_db
def test_product_file_certificate_type() -> None:
    """file_type=certificate is allowed (market-analysis: certificates P0)."""
    from catalog.models import ProductFile

    sku = _make_sku()
    uploaded = SimpleUploadedFile(
        "cert.pdf",
        _pdf_bytes(128),
        content_type="application/pdf",
    )
    pf = ProductFile.objects.create(
        sku=sku,
        title="Сертификат соответствия",
        file=uploaded,
        file_type=ProductFile.FileType.CERTIFICATE,
    )
    assert pf.file_type == "certificate"


@pytest.mark.django_db
def test_product_file_cascade_on_sku_delete() -> None:
    """Deleting SKU cascades to its ProductFile rows."""
    from catalog.models import SKU, ProductFile

    sku = _make_sku()
    uploaded = SimpleUploadedFile(
        "d.pdf",
        _pdf_bytes(64),
        content_type="application/pdf",
    )
    ProductFile.objects.create(
        sku=sku,
        title="D",
        file=uploaded,
        file_type=ProductFile.FileType.DATASHEET,
    )
    sku_pk = sku.pk
    sku.delete()
    assert ProductFile.objects.filter(sku_id=sku_pk).count() == 0
    assert not SKU.objects.filter(pk=sku_pk).exists()


@pytest.mark.django_db
def test_product_file_str() -> None:
    """__str__ is readable: title + sku_code."""
    from catalog.models import ProductFile

    sku = _make_sku()
    uploaded = SimpleUploadedFile(
        "d.pdf",
        _pdf_bytes(64),
        content_type="application/pdf",
    )
    pf = ProductFile.objects.create(
        sku=sku,
        title="Паспорт",
        file=uploaded,
        file_type=ProductFile.FileType.DATASHEET,
    )
    text = str(pf)
    assert "Паспорт" in text
    assert sku.sku_code in text


@pytest.mark.django_db
def test_product_file_default_is_published() -> None:
    """is_published defaults to True (public download on PDP)."""
    from catalog.models import ProductFile

    sku = _make_sku()
    uploaded = SimpleUploadedFile(
        "d.pdf",
        _pdf_bytes(64),
        content_type="application/pdf",
    )
    pf = ProductFile.objects.create(
        sku=sku,
        title="D",
        file=uploaded,
        file_type=ProductFile.FileType.OTHER,
    )
    assert pf.is_published is True


@pytest.mark.django_db
def test_product_protect_blocks_delete_with_sku() -> None:
    """Product with SKU (and files) cannot be deleted (PROTECT on SKU.product).

    Sanity: ProductFile does not weaken existing PROTECT chain.
    """
    from catalog.models import Product, ProductFile

    sku = _make_sku()
    product = sku.product
    uploaded = SimpleUploadedFile(
        "d.pdf",
        _pdf_bytes(64),
        content_type="application/pdf",
    )
    ProductFile.objects.create(
        sku=sku,
        title="D",
        file=uploaded,
        file_type=ProductFile.FileType.DATASHEET,
    )
    with pytest.raises(ProtectedError):
        product.delete()
    assert Product.objects.filter(pk=product.pk).exists()


def test_validate_pdf_upload_accepts_file_like_without_content_type() -> None:
    """BytesIO-like upload without content_type still checked via magic+ext."""
    from catalog.validators import validate_pdf_upload

    # Some ETL paths pass a bare file-like; content_type may be missing.
    buf = BytesIO(_pdf_bytes(128))
    buf.name = "etl-import.pdf"
    validate_pdf_upload(buf)
