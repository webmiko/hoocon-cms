"""Enrich all Hoocon BV* ball valves from the Tilda store CSV (BV215 template)."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.series_copy_ball_valves import apply_all_ball_valve_enrichment


class Command(BaseCommand):
    """Apply BV215-style cards, copy, and galleries to every BV* series."""

    help = (
        "Enrich all ball-valve series (BV215…BV350): description, "
        "attribute cards, compatible drives, bracket, gallery photos."
    )

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Rewrite copy/attrs only; do not download gallery photos.",
        )
        parser.add_argument(
            "--series",
            action="append",
            default=[],
            help="Limit to series code(s), e.g. --series BV220 --series BV315.",
        )
        parser.add_argument(
            "--csv",
            type=str,
            default="",
            help="Optional path to Tilda store CSV (default: sibling hoocon export).",
        )

    def handle(self, *args: object, **options: object) -> None:
        series = tuple(str(s).upper() for s in (options.get("series") or []))
        csv_raw = str(options.get("csv") or "").strip()
        csv_path = Path(csv_raw).expanduser() if csv_raw else None
        try:
            stats = apply_all_ball_valve_enrichment(
                import_images=not bool(options.get("skip_images")),
                series_codes=series or None,
                csv_path=csv_path,
            )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        if stats["products"] == 0:
            self.stderr.write(self.style.ERROR("No ball-valve products enriched"))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Ball valves enriched: series={stats['series']}, "
                f"products={stats['products']}, skus={stats['skus']}, "
                f"attr_writes={stats['attributes']}, "
                f"images_created={stats['images_created']}, "
                f"images_failed={stats['images_failed']}",
            ),
        )
