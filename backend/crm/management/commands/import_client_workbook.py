"""Load a client template or a niche workbook into CRM cards."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from crm.client_import import ClientImportError, import_clients_xlsx

User = get_user_model()


class Command(BaseCommand):
    """Import one or more xlsx files. Existing emails are not overwritten."""

    help = (
        "Создать карточки компаний и клиентов из xlsx (шаблон или подборка). "
        "Пример на проде: import_client_workbook "
        '--assignee assistant@hoocon.ru --pin-rules "Мир климата 11.11.26.xlsx"'
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("paths", nargs="+", help="Пути к .xlsx")
        parser.add_argument(
            "--assignee",
            metavar="EMAIL",
            help="Ответственный менеджер (email или логин), например assistant@hoocon.ru",
        )
        parser.add_argument(
            "--pin-rules",
            action="store_true",
            help="Создать закрепления компания→менеджер для маршрутизации заявок",
        )

    def handle(self, *args: object, **options: object) -> None:
        paths = options["paths"]
        assert isinstance(paths, list)
        pin_rules = bool(options.get("pin_rules"))
        assignee = self._resolve_assignee(options.get("assignee"))
        if pin_rules and assignee is None:
            raise CommandError("Для --pin-rules укажите --assignee.")
        for raw in paths:
            path = Path(str(raw))
            if not path.is_file():
                raise CommandError(f"Файл не найден: {path}")
            try:
                with path.open("rb") as handle:
                    report = import_clients_xlsx(
                        handle,
                        assignee=assignee,
                        pin_lead_rules=pin_rules,
                    )
            except ClientImportError as exc:
                raise CommandError(f"{path.name}: {exc}") from exc
            self.stdout.write(f"{path.name}: {report.summary()}")

    def _resolve_assignee(self, value: object) -> Any | None:
        if not value:
            return None
        key = str(value).strip()
        if "@" in key:
            user = User.objects.filter(email__iexact=key, is_staff=True).first()
        else:
            user = User.objects.filter(username__iexact=key, is_staff=True).first()
        if user is None:
            raise CommandError(f"Сотрудник не найден: {key}")
        return user
