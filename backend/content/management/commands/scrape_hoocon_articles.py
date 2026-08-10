"""Import articles + cover images from https://hoocon.ru/statyi (Tilda feed)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.webp import convert_bytes_to_webp
from content.etl.tilda_articles import (
    DEFAULT_FEED_UID,
    ScrapedArticle,
    collect_image_urls,
    download_bytes,
    rewrite_image_urls,
    scrape_all_articles,
)
from content.models import Article

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Pull all Tilda blog posts into ``content.Article`` with local covers."""

    help = "Scrape https://hoocon.ru/statyi articles and images into CMS"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--feed-uid",
            default=DEFAULT_FEED_UID,
            help="Tilda feeduid (default: Общие статьи on /statyi)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and print plan without writing DB/media",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Do not download cover/inline images",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        skip_images = bool(options["skip_images"])
        feed_uid = str(options["feed_uid"]).strip() or DEFAULT_FEED_UID

        self.stdout.write(f"Fetching feed {feed_uid}…")
        scraped = scrape_all_articles(feed_uid)
        self.stdout.write(f"Posts: {len(scraped)}")

        created = updated = 0
        for item in scraped:
            self.stdout.write(f"  {item.slug}: {item.title[:70]}")
            if dry_run:
                continue
            was_created = self._upsert(item, skip_images=skip_images)
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"articles created={created} updated={updated} dry_run={dry_run}",
            ),
        )

    def _upsert(self, item: ScrapedArticle, *, skip_images: bool) -> bool:
        """Create or update one Article; return True if created."""
        with transaction.atomic():
            article, created = Article.objects.get_or_create(
                slug=item.slug,
                defaults={
                    "title": item.title,
                    "body": item.body_html,
                    "excerpt": item.excerpt,
                    "is_published": True,
                    "published_at": item.published_at,
                },
            )
            if not created:
                article.title = item.title
                article.body = item.body_html
                article.excerpt = item.excerpt
                article.is_published = True
                if item.published_at is not None:
                    article.published_at = item.published_at
                article.save()

            if skip_images:
                return created

            url_map = self._import_images(article, item)
            if url_map:
                new_body = rewrite_image_urls(article.body, url_map)
                if new_body != article.body:
                    article.body = new_body
                    article.save(update_fields=["body", "updated_at"])
            return created

    def _import_images(
        self,
        article: Article,
        item: ScrapedArticle,
    ) -> dict[str, str]:
        """Download cover + inline images; return remote→local URL map."""
        mapping: dict[str, str] = {}
        candidates = collect_image_urls(item.body_html, item.cover_url)
        for remote in candidates:
            try:
                raw = download_bytes(remote)
                webp = convert_bytes_to_webp(raw)
            except Exception as exc:  # noqa: BLE001 — one bad image must not abort
                logger.warning("image failed %s: %s", remote, exc)
                self.stderr.write(f"    skip image {remote}: {exc}")
                continue

            basename = _safe_basename(remote)
            if remote == item.cover_url:
                article.cover.save(basename, ContentFile(webp), save=True)
                if article.cover:
                    mapping[remote] = article.cover.url
                continue

            stored = default_storage.save(
                f"article_covers/{article.slug}/{basename}",
                ContentFile(webp),
            )
            mapping[remote] = default_storage.url(stored)
        return mapping


def _safe_basename(url: str) -> str:
    """Derive a short WebP filename from a remote URL path."""
    name = Path(urlparse(url).path).name or "image.jpg"
    stem = Path(name).stem[:80] or "image"
    return f"{stem}.webp"
