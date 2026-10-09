"""Import articles + cover images from https://hoocon.ru/statyi (Tilda feed).

Default run only creates posts that are not in the CMS yet; ``--force``
refreshes texts of existing ones but never re-publishes a hidden post.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.webp import convert_bytes_to_webp
from content.etl.scrape_import import fetch_images, store_images
from content.etl.tilda_articles import (
    DEFAULT_FEED_UID,
    ScrapedArticle,
    rewrite_image_urls,
    scrape_all_articles,
)
from content.models import Article


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
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite title/body/excerpt of posts already in the CMS",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        skip_images = bool(options["skip_images"])
        force = bool(options["force"])
        feed_uid = str(options["feed_uid"]).strip() or DEFAULT_FEED_UID

        self.stdout.write(f"Fetching feed {feed_uid}…")
        scraped = scrape_all_articles(feed_uid)
        self.stdout.write(f"Posts: {len(scraped)}")

        counts = {"created": 0, "updated": 0, "kept": 0}
        for item in scraped:
            self.stdout.write(f"  {item.slug}: {item.title[:70]}")
            if dry_run:
                continue
            counts[self._upsert(item, skip_images=skip_images, force=force)] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"articles created={counts['created']} updated={counts['updated']} "
                f"kept={counts['kept']} dry_run={dry_run}",
            ),
        )

    def _upsert(self, item: ScrapedArticle, *, skip_images: bool, force: bool) -> str:
        """Create (or with ``force`` refresh) one Article; return the action."""
        if not force and Article.objects.filter(slug=item.slug).exists():
            return "kept"
        images = (
            []
            if skip_images
            else fetch_images(item, to_webp=lambda raw, _url: convert_bytes_to_webp(raw), warn=self.stderr.write)
        )
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
                if item.published_at is not None:
                    article.published_at = item.published_at
                article.save()

            url_map = store_images(
                cover=article.cover,
                cover_url=item.cover_url,
                folder=f"article_covers/{article.slug}",
                images=images,
            )
            if url_map:
                new_body = rewrite_image_urls(article.body, url_map)
                if new_body != article.body:
                    article.body = new_body
                    article.save(update_fields=["body", "updated_at"])
        return "created" if created else "updated"
