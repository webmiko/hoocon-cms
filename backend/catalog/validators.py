"""Upload validators for catalog.ProductFile (PDF).

Spec: docs/security-baseline.md §1; docs/data-quality-etl.md §4.3;
БЗ Инъекции-и-валидация-ввода.md (File Upload).

Чистые функции — без Django ORM. Переиспользуются Admin / API / ETL.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.exceptions import ValidationError

# Лимит PDF datasheet/сертификата (20 MiB). Крупнее — quarantine в ETL.
MAX_PRODUCT_FILE_SIZE_BYTES: int = 20 * 1024 * 1024
ALLOWED_PDF_MIME: str = "application/pdf"
ALLOWED_PDF_EXTENSION: str = ".pdf"
PDF_MAGIC_PREFIX: bytes = b"%PDF"

_ENCODED_SEPARATORS: tuple[str, ...] = ("%2f", "%5c")


def sanitize_upload_filename(filename: str) -> str:
    """Return a safe basename for storage; reject path traversal.

    Args:
        filename: raw client/ETL filename (may contain directories).

    Returns:
        Basename only (no directory components).

    Raises:
        ValidationError: empty name, null byte, encoded slash, or `..` segment.
    """
    if filename is None or not str(filename).strip():
        raise ValidationError("Имя файла не может быть пустым.")

    raw = str(filename)
    if "\x00" in raw:
        raise ValidationError("Имя файла содержит недопустимый null-байт.")

    lowered = raw.lower()
    if any(marker in lowered for marker in _ENCODED_SEPARATORS):
        raise ValidationError("Имя файла содержит path traversal.")

    # Segment-aware: reject `..` as a path component, not `report..v2.pdf`.
    normalized = raw.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if any(part == ".." for part in parts):
        raise ValidationError("Имя файла содержит path traversal.")
    if not parts:
        raise ValidationError("Имя файла недопустимо после очистки пути.")

    base = parts[-1].strip()
    if not base or base in {".", ".."}:
        raise ValidationError("Имя файла недопустимо после очистки пути.")

    return base


def _upload_size(uploaded: Any) -> int:
    """Best-effort size for UploadedFile / file-like objects."""
    size = getattr(uploaded, "size", None)
    if isinstance(size, int):
        return size
    pos = uploaded.tell()
    uploaded.seek(0, os.SEEK_END)
    end = uploaded.tell()
    uploaded.seek(pos)
    return end


def _read_magic(uploaded: Any, n: int = 5) -> bytes:
    """Read first `n` bytes and rewind the file pointer."""
    pos = uploaded.tell()
    uploaded.seek(0)
    magic = uploaded.read(n)
    uploaded.seek(pos)
    return magic if isinstance(magic, bytes) else bytes(magic)


def validate_pdf_upload(uploaded: Any) -> None:
    """Validate PDF upload: extension, MIME (if set), magic bytes, size.

    Args:
        uploaded: Django UploadedFile or file-like with `.name` and read/seek.

    Raises:
        ValidationError: on empty, wrong type, spoofed MIME, or oversize.
    """
    name = getattr(uploaded, "name", "") or ""
    safe_name = sanitize_upload_filename(name)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext != ALLOWED_PDF_EXTENSION:
        raise ValidationError(f"Допустимо только расширение {ALLOWED_PDF_EXTENSION}, получено: {ext!r}.")

    content_type = getattr(uploaded, "content_type", None)
    if content_type and content_type != ALLOWED_PDF_MIME:
        raise ValidationError(f"Допустимый MIME: {ALLOWED_PDF_MIME}, получено: {content_type!r}.")

    size = _upload_size(uploaded)
    if size <= 0:
        raise ValidationError("Файл пуст (size must be > 0).")
    if size > MAX_PRODUCT_FILE_SIZE_BYTES:
        raise ValidationError(f"Файл превышает лимит {MAX_PRODUCT_FILE_SIZE_BYTES} байт (получено {size}).")

    magic = _read_magic(uploaded, len(PDF_MAGIC_PREFIX))
    if not magic.startswith(PDF_MAGIC_PREFIX):
        raise ValidationError("Файл не является PDF (magic bytes).")
