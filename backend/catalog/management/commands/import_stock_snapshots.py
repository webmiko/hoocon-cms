"""Store dated 1C stock workbooks as snapshots.

Live ``SKU.stock_qty`` changes only for the newest file when ``--live-latest``
is set. Older files stay history.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.stock_import import StockImportError, import_stock_xlsx
from catalog.etl.stock_snapshots import stock_date_from_filename


class Command(BaseCommand):
    """Load one or more «Остатки товаров …» workbooks."""

    help = "Сохранить выгрузки остатков 1С как снимки по дате из имени файла."

    def add_arguments(self, parser) -> None:
        parser.add_argument("files", nargs="+", help="Пути к .xlsx")
        parser.add_argument(
            "--live-latest",
            action="store_true",
            help="Самый новый файл также записать в текущий остаток артикулов.",
        )

    def handle(self, *args, **options) -> None:
        dated: list[tuple] = []
        for raw in options["files"]:
            path = Path(raw)
            if not path.is_file():
                raise CommandError(f"Файл не найден: {path}")
            taken_on = stock_date_from_filename(path.name)
            if taken_on is None:
                raise CommandError(f"В имени нет даты: {path.name}")
            dated.append((taken_on, path))
        dated.sort(key=lambda item: item[0])
        newest = dated[-1][0]
        live_latest = bool(options["live_latest"])
        for taken_on, path in dated:
            apply_live = live_latest and taken_on == newest
            try:
                with path.open("rb") as handle:
                    report = import_stock_xlsx(
                        handle,
                        taken_on=taken_on,
                        source_name=path.name,
                        apply_live=apply_live,
                    )
            except StockImportError as exc:
                raise CommandError(f"{path.name}: {exc}") from exc
            live = f", в текущий остаток {report.updated}" if apply_live else ""
            self.stdout.write(f"{taken_on:%d.%m.%Y} {path.name}{live}")
