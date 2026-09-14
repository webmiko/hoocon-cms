"""Seed staff Wiki pages from ``content/fixtures/wiki/`` HTML files."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from content.models import WikiDocument

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "wiki"

WIKI_SEEDS: tuple[dict[str, str | int], ...] = (
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


class Command(BaseCommand):
    """Create or refresh WikiDocument rows from bundled HTML fixtures."""

    help = "Seed staff Wiki pages (HTML dashboards) from content/fixtures/wiki/."

    def handle(self, *args: object, **options: object) -> None:
        del args, options
        for seed in WIKI_SEEDS:
            fixture_name = str(seed["fixture"])
            path = _FIXTURES_DIR / fixture_name
            if not path.is_file():
                self.stderr.write(self.style.ERROR(f"Missing fixture: {path}"))
                continue
            body = path.read_text(encoding="utf-8")
            obj, created = WikiDocument.objects.update_or_create(
                slug=str(seed["slug"]),
                defaults={
                    "title": str(seed["title"]),
                    "category": str(seed["category"]),
                    "summary": str(seed["summary"]),
                    "body": body,
                    "sort_order": int(seed["sort_order"]),
                    "is_active": True,
                },
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(f"{verb} Wiki: {obj.slug} ({len(body):,} bytes HTML)")
