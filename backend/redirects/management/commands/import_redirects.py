"""Import Redirect rows from project seed CSV files."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from redirects.services import load_redirects_from_csv

DEFAULT_SEEDS = (
    "docs/redirects-slug-typo-seed.csv",
    "docs/redirects-tproduct-seed.csv",
)


class Command(BaseCommand):
    """Load SEO redirect seeds into the Redirect table."""

    help = "Import Redirect rows from CSV seeds (typo slugs + Tilda tproduct)."

    def add_arguments(self, parser: object) -> None:
        """Register CLI flags."""
        parser.add_argument(  # type: ignore[attr-defined]
            "paths",
            nargs="*",
            type=str,
            help="Optional CSV paths (default: docs typo + tproduct seeds).",
        )
        parser.add_argument(  # type: ignore[attr-defined]
            "--dry-run",
            action="store_true",
            help="Validate CSV only; do not write to the database.",
        )

    def handle(self, *args: object, **options: object) -> None:
        """Run import for each CSV path."""
        dry_run = bool(options.get("dry_run"))
        raw_paths = options.get("paths") or []
        repo_root = Path(__file__).resolve().parents[4]
        if raw_paths:
            paths = [Path(str(p)) for p in raw_paths]  # type: ignore[union-attr]
        else:
            paths = [repo_root / rel for rel in DEFAULT_SEEDS]

        grand_total = {"created": 0, "updated": 0, "skipped": 0, "total": 0}
        for path in paths:
            try:
                stats = load_redirects_from_csv(path, dry_run=dry_run)
            except (OSError, ValueError) as exc:
                raise CommandError(str(exc)) from exc
            for key in grand_total:
                grand_total[key] += stats[key]
            self.stdout.write(
                f"{path}: created={stats['created']} updated={stats['updated']} "
                f"total={stats['total']}" + (" (dry-run)" if dry_run else "")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: created={grand_total['created']} updated={grand_total['updated']} total={grand_total['total']}"
            )
        )
