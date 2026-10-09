"""Content-hash helpers for ETL file attachments (PDF manuals, images)."""

from __future__ import annotations

import hashlib

from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile

from catalog.models import ProductFile

_CHUNK = 1024 * 1024


def stored_sha256(field: FieldFile) -> str | None:
    """Digest of the stored file, or ``None`` when it is missing/unreadable."""
    if not field or not field.name:
        return None
    try:
        if not field.storage.exists(field.name):
            return None
        with field.storage.open(field.name, "rb") as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except OSError:
        return None


def refresh_product_file(existing: ProductFile, *, basename: str, payload: bytes) -> bool:
    """Re-upload ``payload`` when the stored PDF differs or is missing.

    Same-size edits are detected (sha256, not size), and a row whose file
    vanished from storage is repaired instead of aborting the batch.

    Returns:
        True when the file was rewritten.
    """
    if stored_sha256(existing.file) == hashlib.sha256(payload).hexdigest():
        return False
    existing.file.save(basename, ContentFile(payload), save=True)
    return True
