"""Idempotent ``ProductImage`` upsert for ETL media jobs.

Rows are keyed by ``(sku, source_url)``. A rerun with the same bytes and
metadata is a ``skip``: no storage write, no card re-render. A photo hidden
in Admin stays hidden (``ProductImage.hidden_by_editor``).
"""

from __future__ import annotations

import hashlib
from typing import Literal

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.file_refresh import stored_sha256
from catalog.models import SKU, ProductImage

UpsertAction = Literal["create", "update", "skip"]

_ALT_MAX = 300


def upsert_sku_image(
    sku: SKU,
    *,
    source_url: str,
    filename: str,
    webp: bytes,
    alt: str,
    sort_order: int,
    dry_run: bool,
) -> tuple[UpsertAction, ProductImage | None]:
    """Create or refresh one ETL image; return the action and the row.

    Args:
        sku: Owner SKU.
        source_url: Stable ETL key of the image.
        filename: Storage basename (``*.webp``).
        webp: Encoded WebP bytes.
        alt: Alt text (trimmed to the model limit).
        sort_order: Gallery position.
        dry_run: Report only — nothing is written.

    Returns:
        ``("create"|"update"|"skip", row)``; in dry-run the row is the
        existing one or ``None``.
    """
    alt = alt[:_ALT_MAX]
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        if existing is None:
            return "create", None
        same = stored_sha256(existing.image) == hashlib.sha256(webp).hexdigest()
        return ("skip" if same and _meta_matches(existing, alt, sort_order) else "update"), existing

    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=alt,
                source_url=source_url,
                sort_order=sort_order,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            return "create", image

        same_file = stored_sha256(existing.image) == hashlib.sha256(webp).hexdigest()
        if same_file and _meta_matches(existing, alt, sort_order):
            return "skip", existing

        existing.alt = alt
        existing.sort_order = sort_order
        existing.is_published = True
        if same_file:
            existing.full_clean()
            existing.save(update_fields=["alt", "sort_order", "is_published", "updated_at"])
            return "update", existing
        existing.image.save(filename, ContentFile(webp), save=False)
        existing.full_clean()
        existing.save()
        return "update", existing


def _meta_matches(image: ProductImage, alt: str, sort_order: int) -> bool:
    published_as_wanted = image.is_published or image.hidden_by_editor
    return image.alt == alt and image.sort_order == sort_order and published_as_wanted
