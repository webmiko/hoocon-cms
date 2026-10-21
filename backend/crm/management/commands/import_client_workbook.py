"""Load a client template or a niche workbook into CRM cards."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from crm.client_import import ClientImportError, import_clients_xlsx


class Command(BaseCommand):
    """Import one or more xlsx files. Existing emails are not overwritten."""

    help = "Создать карточки компаний и клиентов из xlsx (шаблон или подборка)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("paths", nargs="+", help="Пути к .xlsx")

    def handle(self, *args: object, **options: object) -> None:
        paths = options["paths"]
        assert isinstance(paths, list)
        for raw in paths:
            path = Path(str(raw))
            if not path.is_file():
                raise CommandError(f"Файл не найден: {path}")
            try:
                with path.open("rb") as handle:
                    report = import_clients_xlsx(handle)
            except ClientImportError as exc:
                raise CommandError(f"{path.name}: {exc}") from exc
            self.stdout.write(f"{path.name}: {report.summary()}")
