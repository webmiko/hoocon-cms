"""Management command: audit / WebP-optimize / prune inferior hero duplicates.

Usage::

    poetry run python manage.py audit_optimize_product_images
    poetry run python manage.py audit_optimize_product_images --dry-run
    poetry run python manage.py audit_optimize_product_images --audit-only
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.product_image_audit import apply_product_image_cleanup, audit_product_images


class Command(BaseCommand):
    """Ensure product gallery heroes are WebP and not duplicated at low res."""

    help = "Audit ProductImage WebP/heroes; convert non-WebP; prune weaker hero dupes."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--audit-only",
            action="store_true",
            help="Print audit JSON without converting or pruning.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run audit and optional cleanup."""
        dry_run = bool(options["dry_run"])
        if options["audit_only"]:
            report = audit_product_images()
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        summary = apply_product_image_cleanup(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        before = summary["before"]
        after = summary["after"]
        pruned = summary["pruned"]
        converted = summary["converted"]
        self.stdout.write(
            f"{prefix}before: non_webp={before['non_webp']} "
            f"weak_heroes={before['weak_heroes']} multi_hero_skus={before['multi_hero_skus']}",
        )
        restored = summary.get("restored_secondary") or {}
        self.stdout.write(
            f"{prefix}converted={converted['converted']} errors={converted['errors']} "
            f"restored_secondary={restored.get('restored', 0)} "
            f"pruned_skus={pruned['skus']} unpublished={pruned['unpublished']}",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}after: non_webp={after['non_webp']} "
                f"weak_heroes={after['weak_heroes']} multi_hero_skus={after['multi_hero_skus']}",
            ),
        )
