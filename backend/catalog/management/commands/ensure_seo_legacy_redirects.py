"""Ensure SEO legacy redirects (Tilda inventory → live nested catalog paths).

Usage::

    poetry run python manage.py ensure_seo_legacy_redirects
    poetry run python manage.py ensure_seo_legacy_redirects --dry-run
    poetry run python manage.py ensure_seo_legacy_redirects --export-nginx
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.seo_legacy_redirects import (
    ensure_article_tpost_redirects,
    ensure_seo_legacy_redirects,
)
from content.article_slug_renames import apply_article_slug_renames
from content.news_slug_renames import apply_news_slug_renames
from redirects.models import Redirect
from redirects.services import render_nginx_map


class Command(BaseCommand):
    """Rebuild Redirect rows for Yandex/Tilda cutover paths."""

    help = (
        "Upsert 301s: flat/tproduct/legacy catalog → live nested SKU; "
        "/statyi/tpost/; news/static inventory. Optionally export nginx map."
    )

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--skip-content-renames",
            action="store_true",
            help="Do not run article/news slug renames.",
        )
        parser.add_argument(
            "--export-nginx",
            action="store_true",
            help="Write deploy/nginx/redirects.map after upserts.",
        )
        default_out = (
            Path(__file__).resolve().parents[4] / "deploy" / "nginx" / "redirects.map"
        )
        parser.add_argument(
            "--output",
            type=str,
            default=str(default_out),
            help="nginx map path when --export-nginx is set.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run ensure + optional content renames and nginx export."""
        dry_run = bool(options["dry_run"])
        prefix = "[dry-run] " if dry_run else ""

        if not options["skip_content_renames"] and not dry_run:
            articles = apply_article_slug_renames()
            news = apply_news_slug_renames()
            self.stdout.write(
                f"{prefix}content renames articles={len(articles)} news={len(news)}",
            )
        elif not options["skip_content_renames"] and dry_run:
            self.stdout.write(f"{prefix}skip content renames (dry-run)")

        tpost_n = ensure_article_tpost_redirects(dry_run=dry_run)
        summary = ensure_seo_legacy_redirects(dry_run=dry_run)
        self.stdout.write(
            f"{prefix}upserted={summary.upserted} products={summary.products} "
            f"skus={summary.skus} tproduct={summary.tproduct} "
            f"static={summary.static} rewritten={summary.rewritten} "
            f"tpost={tpost_n}",
        )

        if options["export_nginx"]:
            if dry_run:
                self.stdout.write(f"{prefix}skip nginx export")
                return
            output = Path(str(options["output"]))
            output.parent.mkdir(parents=True, exist_ok=True)
            qs = list(Redirect.objects.filter(is_active=True).order_by("from_path"))
            output.write_text(render_nginx_map(qs), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Wrote {len(qs)} rules → {output}"))
