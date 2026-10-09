"""Import news + cover images from https://hoocon.ru/news (Tilda feed).

Default run only creates posts that are not in the CMS yet; ``--force``
refreshes texts of existing ones but never re-publishes a hidden post.
Legacy redirects are created once and never re-enabled over an Admin edit.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.webp import convert_bytes_to_webp
from content.etl.scrape_import import fetch_images, store_images
from content.etl.tilda_articles import (
    NEWS_FEED_UID,
    ScrapedArticle,
    rewrite_image_urls,
    scrape_all_articles,
)
from content.models import News
from content.news_slug_renames import apply_news_slug_renames, canonical_news_slug
from redirects.models import Redirect

_SVG_EMBED_RE = re.compile(
    r"data:image/(?:png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)",
    re.I,
)


def _bytes_to_webp_tolerant(raw: bytes, remote: str) -> bytes:
    """Convert image bytes to WebP; for SVG, extract the largest embedded raster."""
    try:
        return convert_bytes_to_webp(raw)
    except Exception:
        if not remote.lower().endswith(".svg") and b"<svg" not in raw[:200].lower():
            raise
        text = raw.decode("utf-8", errors="ignore")
        embeds = _SVG_EMBED_RE.findall(text)
        if not embeds:
            raise
        import base64

        best = max(embeds, key=len)
        return convert_bytes_to_webp(base64.b64decode(best))


class Command(BaseCommand):
    """Pull all Tilda news posts into ``content.News`` with local covers."""

    help = "Scrape https://hoocon.ru/news posts and images into CMS"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--feed-uid",
            default=NEWS_FEED_UID,
            help="Tilda feeduid (default: /news feed)",
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
            help="Overwrite title/body of posts already in the CMS",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        skip_images = bool(options["skip_images"])
        force = bool(options["force"])
        feed_uid = str(options["feed_uid"]).strip() or NEWS_FEED_UID

        self.stdout.write(f"Fetching news feed {feed_uid}…")
        scraped = scrape_all_articles(feed_uid)
        self.stdout.write(f"Posts: {len(scraped)}")

        counts = {"created": 0, "updated": 0, "kept": 0}
        for item in scraped:
            item = replace(item, slug=canonical_news_slug(item.slug))
            self.stdout.write(f"  {item.slug}: {item.title[:70]}")
            if dry_run:
                continue
            counts[self._upsert(item, skip_images=skip_images, force=force)] += 1
            self._ensure_redirects(item)

        if not dry_run:
            for old_slug, new_slug in apply_news_slug_renames():
                self.stdout.write(f"news slug: {old_slug} → {new_slug} (+301)")
            Redirect.objects.get_or_create(
                from_path="/news",
                defaults={
                    "to_path": "/novosti",
                    "status_code": 301,
                    "is_active": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"news created={counts['created']} updated={counts['updated']} "
                f"kept={counts['kept']} dry_run={dry_run}",
            ),
        )

    def _upsert(self, item: ScrapedArticle, *, skip_images: bool, force: bool) -> str:
        """Create (or with ``force`` refresh) one News row; return the action."""
        if not force and News.objects.filter(slug=item.slug).exists():
            return "kept"
        images = [] if skip_images else fetch_images(item, to_webp=_bytes_to_webp_tolerant, warn=self.stderr.write)
        with transaction.atomic():
            news, created = News.objects.get_or_create(
                slug=item.slug,
                defaults={
                    "title": item.title,
                    "body": item.body_html,
                    "is_published": True,
                    "published_at": item.published_at,
                },
            )
            if not created:
                news.title = item.title
                news.body = item.body_html
                if item.published_at is not None:
                    news.published_at = item.published_at
                news.save()

            url_map = store_images(
                cover=news.cover,
                cover_url=item.cover_url,
                folder=f"news_covers/{news.slug}",
                images=images,
            )
            if url_map:
                new_body = rewrite_image_urls(news.body, url_map)
                if new_body != news.body:
                    news.body = new_body
                    news.save(update_fields=["body", "updated_at"])
        return "created" if created else "updated"

    @staticmethod
    def _ensure_redirects(item: ScrapedArticle) -> None:
        """Map legacy /news/… paths to canonical /novosti/<slug>."""
        from urllib.parse import urlparse

        raw = (item.source_url or "").strip()
        if not raw:
            return
        parsed = urlparse(raw if "://" in raw else f"https://hoocon.ru{raw}")
        legacy = parsed.path.rstrip("/") or "/"
        if not legacy.startswith("/news/"):
            return
        to_path = f"/novosti/{item.slug}"
        if legacy == to_path:
            return
        Redirect.objects.get_or_create(
            from_path=legacy,
            defaults={
                "to_path": to_path,
                "status_code": 301,
                "is_active": True,
            },
        )
