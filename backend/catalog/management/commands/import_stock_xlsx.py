"""Import SKU stock quantities from a 1C Excel (.xlsx) file."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.stock_import import StockImportError, import_stock_xlsx


class Command(BaseCommand):
    """Apply warehouse stock from an XLSX with Артикул + Остатки columns."""

    help = (
        "Import stock quantities from Excel (.xlsx). "
        "Columns: «Артикул» and «Свободно»/«Остатки»/«Остаток». "
        "Unknown SKUs are ignored."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "path",
            type=str,
            help="Path to the .xlsx stock export.",
        )

    def handle(self, *args, **options) -> None:
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"File not found: {path}")
        if path.suffix.lower() != ".xlsx":
            raise CommandError("Only .xlsx files are supported.")
        try:
            with path.open("rb") as fh:
                report = import_stock_xlsx(fh)
        except StockImportError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(report.summary()))
