"""Собрать единый текстовый файл БЗ для GigaChat (ветки @BRANCH → commit → prod)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from supportchat.gigachat.kb_branches import load_kb_branches
from supportchat.gigachat.kb_build import write_packaged_kb
from supportchat.gigachat.kb_text import PACKAGED_KB_PATH
from supportchat.gigachat.manuals_kb import default_manuals_ru_dir


class Command(BaseCommand):
    """Build ``supportchat/data/gigachat_kb.txt`` with @BRANCH markers."""

    help = (
        "Собрать единый файл БЗ бота (ветки @BRANCH, умный поиск) из CMS, "
        "_manuals-ru и _инструкции-pdf. Коммитится и уезжает на прод."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help=f"Путь к TXT (по умолчанию {PACKAGED_KB_PATH}).",
        )
        parser.add_argument(
            "--manuals-ru",
            type=str,
            default="",
            help="Каталог _manuals-ru (по умолчанию в корне репозитория).",
        )
        parser.add_argument(
            "--manuals-pdf",
            type=str,
            default="",
            help="Каталог _инструкции-pdf (по умолчанию symlink в корне).",
        )
        parser.add_argument(
            "--no-site",
            action="store_true",
            help="Не включать снимок CMS/каталога — только мануалы и policy.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        ru_dir = Path(options["manuals_ru"]).expanduser() if options["manuals_ru"] else None
        pdf_dir = Path(options["manuals_pdf"]).expanduser() if options["manuals_pdf"] else None
        output = Path(options["output"]).expanduser() if options["output"] else None

        check_dir = ru_dir or default_manuals_ru_dir()
        if not check_dir.is_dir():
            raise CommandError(
                f"Нет каталога {check_dir}. Подключите _manuals-ru локально и повторите.",
            )

        try:
            path = write_packaged_kb(
                output,
                manuals_ru_dir=ru_dir,
                manuals_pdf_dir=pdf_dir,
                include_site=not options["no_site"],
            )
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        load_kb_branches.cache_clear()
        branches = load_kb_branches(path)
        manual_count = sum(1 for branch in branches if branch.id.startswith("manual."))
        size_kb = path.stat().st_size // 1024
        self.stdout.write(
            self.style.SUCCESS(
                f"OK: {path} — {len(branches)} веток (мануалы {manual_count}), ~{size_kb} KB",
            ),
        )
