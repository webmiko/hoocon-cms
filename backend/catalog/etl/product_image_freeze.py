"""Freeze approved ProductImage rows and verify their files against a manifest."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any, Literal

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from catalog.etl.file_refresh import stored_sha256
from catalog.models import ProductImage

FreezeScope = Literal["schemes", "all"]

SCHEME_FILENAME_TOKENS: tuple[str, ...] = (
    "-wiring",
    "-dimensions",
    "-size",
    "-aux",
    "-settings",
)
MANIFEST_FIELDS: tuple[str, ...] = ("sku", "image", "sha256", "size_bytes", "locked_at")
FREEZE_ACTOR = "freeze_product_images"
_CHUNK = 1024 * 1024


def freeze_queryset(
    *,
    scope: FreezeScope,
    sku_codes: tuple[str, ...] = (),
    series_prefixes: tuple[str, ...] = (),
    exclude_sku_codes: tuple[str, ...] = (),
) -> QuerySet[ProductImage]:
    """Build the ProductImage queryset selected by freeze CLI filters."""
    qs = ProductImage.objects.select_related("sku").order_by("sku__sku_code", "sort_order", "id")
    if scope == "schemes":
        scheme_q: Q | None = None
        for token in SCHEME_FILENAME_TOKENS:
            part = Q(image__icontains=token)
            scheme_q = part if scheme_q is None else scheme_q | part
        if scheme_q is not None:
            qs = qs.filter(scheme_q)

    selected_q: Q | None = None
    for code in sku_codes:
        part = Q(sku__sku_code__iexact=code)
        selected_q = part if selected_q is None else selected_q | part
    for prefix in series_prefixes:
        part = Q(sku__sku_code__istartswith=prefix)
        selected_q = part if selected_q is None else selected_q | part
    if selected_q is not None:
        qs = qs.filter(selected_q)

    for code in exclude_sku_codes:
        qs = qs.exclude(sku__sku_code__iexact=code)
    return qs


def freeze_product_images(
    *,
    scope: FreezeScope,
    dry_run: bool,
    reports_dir: Path,
    sku_codes: tuple[str, ...] = (),
    series_prefixes: tuple[str, ...] = (),
    exclude_sku_codes: tuple[str, ...] = (),
    actor: str = FREEZE_ACTOR,
) -> dict[str, Any]:
    """Lock selected rows and, when applying, write a sha256 manifest."""
    qs = freeze_queryset(
        scope=scope,
        sku_codes=sku_codes,
        series_prefixes=series_prefixes,
        exclude_sku_codes=exclude_sku_codes,
    )
    rows = list(qs)
    already_locked = sum(1 for row in rows if row.image_locked)
    to_lock_ids = [int(row.pk) for row in rows if not row.image_locked]
    now = timezone.now()
    locked_now = 0

    if not dry_run and to_lock_ids:
        with transaction.atomic():
            locked_now = ProductImage.objects.filter(pk__in=to_lock_ids, image_locked=False).update(
                image_locked=True,
                locked_at=now,
                locked_by=actor,
            )

    manifest_path: Path | None = None
    if not dry_run:
        rows = list(qs.all())
        reports_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = _write_manifest(rows, reports_dir=reports_dir, stamp=now)

    return {
        "scope": scope,
        "dry_run": dry_run,
        "matched": len(rows),
        "would_lock": len(to_lock_ids),
        "locked": locked_now,
        "already_locked": already_locked,
        "rows": rows,
        "manifest": manifest_path,
    }


def _write_manifest(rows: list[ProductImage], *, reports_dir: Path, stamp: Any) -> Path:
    """Write one unique CSV manifest for the locked selection."""
    base = reports_dir / f"product-images-manifest-{stamp:%Y%m%dT%H%M%SZ}.csv"
    path = base
    counter = 2
    while path.exists():
        path = base.with_name(f"{base.stem}-{counter}{base.suffix}")
        counter += 1

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MANIFEST_FIELDS))
        writer.writeheader()
        for row in rows:
            digest = stored_sha256(row.image) or ""
            size = _stored_size(row)
            writer.writerow(
                {
                    "sku": row.sku.sku_code if row.sku_id else "",
                    "image": row.image.name or "",
                    "sha256": digest,
                    "size_bytes": size,
                    "locked_at": row.locked_at.isoformat() if row.locked_at else "",
                },
            )
    return path


def _stored_size(row: ProductImage) -> int:
    """Return stored file size in bytes, or zero when unreadable."""
    if not row.image or not row.image.name:
        return 0
    try:
        return int(row.image.size)
    except (OSError, ValueError):
        return 0


def default_reports_dir() -> Path:
    """Repository-level reports/ directory (backend is settings.BASE_DIR)."""
    return Path(settings.BASE_DIR).parent / "reports"


def latest_manifest(reports_dir: Path) -> Path | None:
    """Return the newest freeze manifest in ``reports_dir``, if present."""
    manifests = sorted(reports_dir.glob("product-images-manifest-*.csv"))
    return manifests[-1] if manifests else None


def verify_product_images_manifest(manifest_path: Path, *, media_root: Path | None = None) -> dict[str, Any]:
    """Compare files under MEDIA_ROOT with a freeze manifest.

    Returns:
        ``rows``, ``checked`` and ``mismatches``; each mismatch has sku, image,
        and reason. The function does not mutate files or database rows.
    """
    root = media_root or Path(settings.MEDIA_ROOT)
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing_columns = [name for name in MANIFEST_FIELDS if name not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"manifest lacks columns: {', '.join(missing_columns)}")
        rows = list(reader)

    mismatches: list[dict[str, str]] = []
    for row in rows:
        rel_name = (row.get("image") or "").strip()
        sku = (row.get("sku") or "").strip()
        rel_path = Path(rel_name)
        if not rel_name or rel_path.is_absolute() or ".." in rel_path.parts:
            mismatches.append({"sku": sku, "image": rel_name, "reason": "invalid-path"})
            continue
        path = root / rel_path
        if not path.is_file():
            mismatches.append({"sku": sku, "image": rel_name, "reason": "missing"})
            continue

        actual_size = path.stat().st_size
        try:
            expected_size = int(row.get("size_bytes") or "0")
        except ValueError:
            expected_size = -1
        reasons: list[str] = []
        if actual_size != expected_size:
            reasons.append("size")
        actual_sha256 = _file_sha256(path)
        if actual_sha256 != (row.get("sha256") or ""):
            reasons.append("sha256")
        if reasons:
            mismatches.append({"sku": sku, "image": rel_name, "reason": "+".join(reasons)})

    return {
        "rows": len(rows),
        "checked": len(rows),
        "mismatches": mismatches,
        "manifest": manifest_path,
        "media_root": root,
    }


def _file_sha256(path: Path) -> str:
    """Hash one local file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
