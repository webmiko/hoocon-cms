"""ETL orchestration command: Tilda JSON → Django catalog.

Spec: docs/data-quality-etl.md §6 — scripts/etl_hoocon_data.py.
Pipeline: extract → normalize → load. Bad rows → quarantine CSV.

Usage:
    python manage.py etl_hoocon \
        --source ../hoocon/data/hoocon_catalog_api.json \
        --quarantine reports/quarantine.csv
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.extract import extract_categories, extract_products
from catalog.etl.load import LoadStats, load_categories, load_product
from catalog.etl.normalize import (
    QuarantineError,
    normalize_category,
    normalize_product,
)
from catalog.etl.quarantine import write_quarantine_csv

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Import Hoocon catalog from Tilda JSON export into Django ORM."""

    help = "Import catalog from Tilda JSON: extract → normalize → load + quarantine"

    def add_arguments(self, parser: Any) -> None:
        """Define CLI arguments."""
        parser.add_argument(
            "--source",
            required=True,
            help="Path to hoocon_catalog_api.json (Tilda export).",
        )
        parser.add_argument(
            "--quarantine",
            default="reports/quarantine.csv",
            help="Output path for quarantined rows CSV.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the ETL pipeline."""
        source_path = Path(options["source"])
        quarantine_path = Path(options["quarantine"])

        if not source_path.exists():
            raise CommandError(f"Source file not found: {source_path}")

        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {source_path}: {exc}") from exc

        quarantined: list[dict[str, Any]] = []

        # ── Categories ───────────────────────────────────────────────
        cat_norm: list[Any] = []
        for cid, name, parent_id in extract_categories(payload):
            try:
                cat_norm.append(
                    normalize_category(cid=cid, name=name, parent_id=parent_id),
                )
            except QuarantineError as exc:
                quarantined.append(
                    {"reason": exc.reason, "payload": {"id": cid, "name": name, **exc.payload}},
                )

        cat_stats, cat_map = load_categories(cat_norm)

        # ── Products ─────────────────────────────────────────────────
        prod_stats = LoadStats()
        for raw_product in extract_products(payload):
            try:
                np = normalize_product(raw_product)
            except QuarantineError as exc:
                quarantined.append(
                    {"reason": exc.reason, "payload": {**exc.payload, **exc.payload}},
                )
                continue
            try:
                ps = load_product(np, category_map=cat_map)
                prod_stats.products_created += ps.products_created
                prod_stats.skus_created += ps.skus_created
                prod_stats.attribute_values_created += ps.attribute_values_created
            except QuarantineError as exc:
                quarantined.append({"reason": exc.reason, "payload": exc.payload})

        # ── Quarantine CSV ────────────────────────────────────────────
        written = write_quarantine_csv(quarantined, quarantine_path)

        self.stdout.write(
            self.style.SUCCESS(
                f"ETL done: categories +{cat_stats.created}, "
                f"products +{prod_stats.products_created}, "
                f"skus +{prod_stats.skus_created}, "
                f"attribute_values +{prod_stats.attribute_values_created}, "
                f"quarantined {written} rows → {quarantine_path}",
            ),
        )
