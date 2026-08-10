"""Import product photos from Tilda Store CSV → ProductImage (WebP).

Usage:
  poetry run python manage.py import_tilda_images \\
    /path/to/store-….csv [--dry-run] [--quality=90]

Matches rows by SKU code (case-insensitive) to catalog.SKU, downloads Photo
URLs from Tilda CDN, converts to WebP (quality ~90), stores under MEDIA_ROOT.
Idempotent via (sku, source_url) unique constraint.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.etl.webp import DEFAULT_WEBP_QUALITY, convert_bytes_to_webp
from catalog.models import SKU, ProductImage

logger = logging.getLogger(__name__)

USER_AGENT = "HooconCMS-ImageImport/1.0 (+https://hoocon.ru)"
DOWNLOAD_TIMEOUT_S = 45
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024


def _parse_photo_urls(photo_field: str) -> list[str]:
    """Split Tilda Photo cell (space-separated absolute URLs)."""
    if not photo_field or not photo_field.strip():
        return []
    urls: list[str] = []
    for part in photo_field.split():
        url = part.strip()
        if url.startswith("https://") or url.startswith("http://"):
            urls.append(url)
    return urls


def _download(url: str) -> bytes:
    """Download image bytes with size cap and timeout."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as resp:  # noqa: S310 — curated CDN URLs
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"Download exceeds {MAX_DOWNLOAD_BYTES} bytes: {url}")
            chunks.append(chunk)
    return b"".join(chunks)


class Command(BaseCommand):
    """Attach Tilda Store CSV photos to matching SKUs as WebP ProductImage."""

    help = "Import product images from Tilda store CSV (WebP, quality≈90)."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "csv_path",
            type=str,
            help="Path to Tilda store export CSV (semicolon-separated).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and match only; do not download or write DB.",
        )
        parser.add_argument(
            "--quality",
            type=int,
            default=DEFAULT_WEBP_QUALITY,
            help=f"WebP quality 1–100 (default {DEFAULT_WEBP_QUALITY}).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Process at most N SKU-rows with photos (0 = all).",
        )

    def handle(self, *args, **options) -> None:  # type: ignore[no-untyped-def]
        csv_path = Path(options["csv_path"]).expanduser().resolve()
        if not csv_path.is_file():
            raise CommandError(f"CSV not found: {csv_path}")

        quality = int(options["quality"])
        if quality < 1 or quality > 100:
            raise CommandError("--quality must be 1–100")

        dry_run = bool(options["dry_run"])
        limit = int(options["limit"] or 0)

        sku_by_code = {sku.sku_code.lower(): sku for sku in SKU.objects.all().only("id", "sku_code", "name")}

        created = 0
        skipped_existing = 0
        skipped_no_sku = 0
        failed = 0
        matched_rows = 0

        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            if not reader.fieldnames or "SKU" not in reader.fieldnames:
                raise CommandError("CSV must include SKU and Photo columns.")

            for row in reader:
                sku_raw = (row.get("SKU") or "").strip()
                if not sku_raw:
                    continue
                urls = _parse_photo_urls(row.get("Photo") or "")
                if not urls:
                    continue

                sku = sku_by_code.get(sku_raw.lower())
                if sku is None:
                    skipped_no_sku += 1
                    self.stdout.write(f"  skip unknown SKU: {sku_raw}")
                    continue

                matched_rows += 1
                if limit and matched_rows > limit:
                    break

                for sort_order, url in enumerate(urls):
                    exists = ProductImage.objects.filter(sku=sku, source_url=url).exists()
                    if exists:
                        skipped_existing += 1
                        continue

                    if dry_run:
                        self.stdout.write(f"  [dry-run] {sku.sku_code} ← {url}")
                        created += 1
                        continue

                    try:
                        raw = _download(url)
                        webp = convert_bytes_to_webp(raw, quality=quality)
                        filename = f"{sku.sku_code.lower()}-{sort_order}.webp"
                        with transaction.atomic():
                            img = ProductImage(
                                sku=sku,
                                alt=sku.name[:300],
                                source_url=url,
                                sort_order=sort_order,
                                is_published=True,
                            )
                            img.image.save(filename, ContentFile(webp), save=False)
                            img.full_clean()
                            img.save()
                        created += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"  + {sku.sku_code} [{sort_order}]"),
                        )
                    except (HTTPError, URLError, OSError, ValueError, ValidationError) as exc:
                        failed += 1
                        logger.warning(
                            "Image import failed for %s %s: %s",
                            sku.sku_code,
                            url,
                            exc,
                        )
                        self.stderr.write(f"  FAIL {sku.sku_code}: {exc}")

        self.stdout.write(
            self.style.NOTICE(
                f"Done. created={created} existing={skipped_existing} "
                f"unknown_sku={skipped_no_sku} failed={failed} dry_run={dry_run}",
            ),
        )
