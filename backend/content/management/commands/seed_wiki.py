"""Seed staff Wiki pages from ``content/fixtures/wiki/`` HTML files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from content.models import WikiDocument

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "wiki"

WIKI_SEEDS: tuple[dict[str, str | int], ...] = (
    {
        "slug": "admin-3-0-manager-guide",
        "title": "Панель управления 3.0 · инструкция для менеджеров",
        "category": "Инструкции",
        "summary": (
            "Полное руководство CRM 3.0: заявки, клиенты, почта, звонки, КП, "
            "заказы, диалоги, отчёт РОП и журнал изменений."
        ),
        "fixture": "admin-3-0-manager-guide.html",
        "sort_order": 1,
    },
    {
        "slug": "mango-telephony-guide",
        "title": "Телефония Mango · звонки из CRM",
        "category": "Инструкции",
        "summary": (
            "Click-to-call из карточки клиента, журнал звонков, записи "
            "разговоров, добавочный менеджера — как пользоваться и что чинить."
        ),
        "fixture": "mango-telephony-guide.html",
        "sort_order": 2,
    },
    {
        "slug": "novosystem-telephony-guide",
        "title": "Телефония Новосистем (UIS) · звонки из CRM",
        "category": "Инструкции",
        "summary": (
            "Виджет Новосистем в интеграциях, настройка ЛК UIS, ID сотрудника, "
            "звонок из карточки клиента, журнал и разбор ошибок."
        ),
        "fixture": "novosystem-telephony-guide.html",
        "sort_order": 3,
    },
    {
        "slug": "ostatki-prodazhi-god-2025-09-2026-08",
        "title": "Анализ остатков и продаж · сен 2025 — авг 2026",
        "category": "Аналитика склада",
        "summary": (
            "Годовой дашборд по месячным отчётам 1С: помесячное сравнение, прогноз "
            "на следующий год, календарь закупок (lead 4 мес), топ SKU и план пополнения."
        ),
        "fixture": "stock-dashboard-year-2025-09-2026-08.html",
        "sort_order": 5,
    },
    {
        "slug": "ostatki-prodazhi-14-09-2026",
        "title": "Анализ остатков и продаж · 10.08–14.09.2026",
        "category": "Аналитика склада",
        "summary": (
            "Дашборд по снимкам остатков: динамика, ходовой товар, "
            "позиции без движения, план пополнения и пояснения «что за цифрами»."
        ),
        "fixture": "stock-dashboard-14-09-2026.html",
        "sort_order": 10,
    },
)


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Command(BaseCommand):
    """Create or refresh WikiDocument rows from bundled HTML fixtures.

    Runs on every web container start, so it must never undo staff work:
    a page whose HTML no longer matches the last seed was edited in Admin
    and is skipped (``--force`` overwrites), and ``is_active`` is only set
    when the page is created.
    """

    help = "Seed staff Wiki pages (HTML dashboards) from content/fixtures/wiki/."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--force", action="store_true", help="Overwrite pages edited in Admin.")

    def handle(self, *args: object, **options: object) -> None:
        force = bool(options.get("force"))
        for seed in WIKI_SEEDS:
            fixture_name = str(seed["fixture"])
            path = _FIXTURES_DIR / fixture_name
            if not path.is_file():
                self.stderr.write(self.style.ERROR(f"Missing fixture: {path}"))
                continue
            body = path.read_text(encoding="utf-8")
            fields = {
                "title": str(seed["title"]),
                "category": str(seed["category"]),
                "summary": str(seed["summary"]),
                "body": body,
                "sort_order": int(seed["sort_order"]),
                "seed_hash": body_hash(body),
            }
            obj = WikiDocument.objects.filter(slug=str(seed["slug"])).first()
            if obj is None:
                obj = WikiDocument.objects.create(slug=str(seed["slug"]), is_active=True, **fields)
                self.stdout.write(f"Created Wiki: {obj.slug} ({len(body):,} bytes HTML)")
                continue
            edited = bool(obj.seed_hash) and body_hash(obj.body) != obj.seed_hash
            if edited and not force:
                self.stdout.write(self.style.WARNING(f"Skipped Wiki: {obj.slug} — edited in Admin (use --force)"))
                continue
            if obj.seed_hash == fields["seed_hash"] and not edited:
                continue
            for name, value in fields.items():
                setattr(obj, name, value)
            obj.save(update_fields=[*fields, "updated_at"])
            self.stdout.write(f"Updated Wiki: {obj.slug} ({len(body):,} bytes HTML)")
