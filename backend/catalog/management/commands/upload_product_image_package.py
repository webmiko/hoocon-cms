"""Apply a reference image upload package (manifest.json + files/) to the database.

Usage::

    poetry run python manage.py upload_product_image_package --package-dir <dir> --dry-run
    poetry run python manage.py upload_product_image_package --package-dir ... --yes
    poetry run python manage.py upload_product_image_package --package-dir ... --yes --allow-skip
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.image_package_upload import upload_package


class Command(BaseCommand):
    """Apply the upload package behind a dry-run gate with rollback snapshot."""

    help = "Upload reference ProductImage package (dry-run gate by default; --yes applies with rollback snapshot)."

    def add_arguments(self, parser: Any) -> None:
        """Register package path, mode and gate flags."""
        parser.add_argument("--package-dir", required=True, help="Directory with manifest.json and files/.")
        parser.add_argument(
            "--rollback-dir",
            default="",
            help="Where rollback snapshots go (default: <package-dir>/rollback/).",
        )
        parser.add_argument(
            "--allow-skip",
            action="store_true",
            help="Permit skip predictions (expected on idempotent reruns; suspicious on first run).",
        )
        parser.add_argument(
            "--expect-counts",
            default="",
            help="Exact expectations like update=112,create=36,unpublish=18,skip=0; mismatch blocks apply.",
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Plan and validate only (default).")
        mode.add_argument("--yes", action="store_true", help="Apply the package after the gate passes.")

    def handle(self, *args: Any, **options: Any) -> None:
        """Plan, gate and optionally apply; exit non-zero on gate anomalies."""
        package_dir = Path(options["package_dir"])
        if not package_dir.is_dir():
            raise CommandError(f"package dir not found: {package_dir}")
        rollback_dir = Path(options["rollback_dir"]) if str(options.get("rollback_dir") or "").strip() else None
        dry_run = not bool(options.get("yes"))

        expect_counts: dict[str, int] = {}
        expect_raw = str(options.get("expect_counts") or "").strip()
        if expect_raw:
            for part in expect_raw.split(","):
                part = part.strip()
                if not part:
                    continue
                key, sep, value = part.partition("=")
                # Строго: опечатка в значении не должна молча снимать контракт.
                if not sep or not key.strip() or not value.strip().isdigit():
                    raise CommandError(f"malformed --expect-counts part: {part!r}")
                expect_counts[key.strip()] = int(value)

        try:
            result = upload_package(
                package_dir,
                dry_run=dry_run,
                allow_skip=bool(options.get("allow_skip")),
                rollback_root=rollback_dir,
                expect_counts=expect_counts or None,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        counts = result["counts"]
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(f"package sha256: {result['manifest_sha256']}")
        self.stdout.write(
            f"{prefix}planned update={counts['update']} create={counts['create']} "
            f"unpublish={counts['unpublish']} skip={counts['skip']}",
        )
        for plan_row in result["plan"]:
            mark = plan_row.fatal or ("skip" if plan_row.skip else plan_row.prediction)
            self.stdout.write(f"  {mark}\t{plan_row.sku_code}\t{plan_row.source_url[-60:]}")
        if result["anomalies"]:
            for anomaly in result["anomalies"]:
                self.stderr.write(f"anomaly: {anomaly}")
            raise CommandError(f"gate anomalies: {len(result['anomalies'])}; resolve or pass --allow-skip for skips")
        if not dry_run:
            applied = result.get("applied") or {}
            self.stdout.write(
                self.style.SUCCESS(
                    f"applied update={applied.get('update', 0)} create={applied.get('create', 0)} "
                    f"unpublish={applied.get('unpublish', 0)} skip={applied.get('skip', 0)} "
                    f"rollback={result['rollback_dir']}",
                ),
            )
