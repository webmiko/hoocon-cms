"""Apply Hoocon copy and cover to the VK community (groups.edit + cover photo).

Usage:
    poetry run python manage.py vk_setup_community --dry-run
    poetry run python manage.py vk_setup_community
    poetry run python manage.py vk_setup_community --no-cover
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from sitesettings.credentials import vk_access_token
from sitesettings.models import SiteSettings
from social.vk_community import (
    apply_community_profile,
    community_cover_path,
    community_description,
    community_status,
    community_title,
)


class Command(BaseCommand):
    help = "Fill VK community description, status, site, phone and cover image."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned text and cover path without calling VK API.",
        )
        parser.add_argument(
            "--no-cover",
            action="store_true",
            help="Update text fields only (skip cover upload).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        token = vk_access_token()
        site = SiteSettings.load()
        group_id = (site.vk_group_id or "").strip().lstrip("-")
        if not token or not group_id.isdigit():
            raise CommandError("VK token and numeric vk_group_id required (Admin or VK_ACCESS_TOKEN).")

        if options["dry_run"]:
            self.stdout.write(f"Title: {community_title()}")
            self.stdout.write(f"Status: {community_status()}")
            self.stdout.write("Description:")
            self.stdout.write(community_description())
            cover = community_cover_path()
            self.stdout.write(f"Cover: {cover or '—'}")
            return

        results = apply_community_profile(
            group_id,
            upload_cover=not options["no_cover"],
        )
        for key, value in results.items():
            if value == "ok" or value == "cover_ok" or value == "skipped":
                self.stdout.write(self.style.SUCCESS(f"{key}: {value}"))
            else:
                self.stdout.write(self.style.ERROR(f"{key}: {value}"))

        if results.get("profile") != "ok":
            raise CommandError("groups.edit failed — check token permissions (manage community).")
        if results.get("cover") not in {"ok", "cover_ok", "skipped"}:
            self.stdout.write(
                self.style.WARNING(
                    "Обложка через API не применилась — добавьте ключу право «Фото» "
                    "или загрузите backend/static/social/vk-community-cover.jpg вручную "
                    "в VK → Управление → Обложка.",
                ),
            )
