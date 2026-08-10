"""Import news + cover images from https://hoocon.ru/news (Tilda feed)."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.webp import convert_bytes_to_webp
from content.etl.tilda_articles import (
    NEWS_FEED_UID,
    ScrapedArticle,
    collect_image_urls,
    download_bytes,
    rewrite_image_urls,
    scrape_all_articles,
)
from content.models import News
from content.news_slug_renames import apply_news_slug_renames, canonical_news_slug
from redirects.models import Redirect

logger = logging.getLogger(__name__)

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

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        skip_images = bool(options["skip_images"])
        feed_uid = str(options["feed_uid"]).strip() or NEWS_FEED_UID

        self.stdout.write(f"Fetching news feed {feed_uid}…")
        scraped = scrape_all_articles(feed_uid)
        self.stdout.write(f"Posts: {len(scraped)}")

        created = updated = 0
        for item in scraped:
            item = replace(item, slug=canonical_news_slug(item.slug))
            self.stdout.write(f"  {item.slug}: {item.title[:70]}")
            if dry_run:
                continue
            was_created = self._upsert(item, skip_images=skip_images)
            if was_created:
                created += 1
            else:
                updated += 1
            self._ensure_redirects(item)

        if not dry_run:
            for old_slug, new_slug in apply_news_slug_renames():
                self.stdout.write(f"news slug: {old_slug} → {new_slug} (+301)")
            Redirect.objects.update_or_create(
                from_path="/news",
                defaults={
                    "to_path": "/novosti",
                    "status_code": 301,
                    "is_active": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"news created={created} updated={updated} dry_run={dry_run}",
            ),
        )

    def _upsert(self, item: ScrapedArticle, *, skip_images: bool) -> bool:
        """Create or update one News row; return True if created."""
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
                news.is_published = True
                if item.published_at is not None:
                    news.published_at = item.published_at
                news.save()

            if skip_images:
                return created

            url_map = self._import_images(news, item)
            if url_map:
                new_body = rewrite_image_urls(news.body, url_map)
                if new_body != news.body:
                    news.body = new_body
                    news.save(update_fields=["body", "updated_at"])
            return created

    def _import_images(
        self,
        news: News,
        item: ScrapedArticle,
    ) -> dict[str, str]:
        """Download cover + inline images; return remote→local URL map."""
        mapping: dict[str, str] = {}
        candidates = collect_image_urls(item.body_html, item.cover_url)
        for remote in candidates:
            try:
                raw = download_bytes(remote)
                webp = _bytes_to_webp_tolerant(raw, remote)
            except Exception as exc:  # noqa: BLE001 — one bad image must not abort
                logger.warning("image failed %s: %s", remote, exc)
                self.stderr.write(f"    skip image {remote}: {exc}")
                continue

            basename = _safe_basename(remote)
            if remote == item.cover_url:
                news.cover.save(basename, ContentFile(webp), save=True)
                if news.cover:
                    mapping[remote] = news.cover.url
                continue

            stored = default_storage.save(
                f"news_covers/{news.slug}/{basename}",
                ContentFile(webp),
            )
            mapping[remote] = default_storage.url(stored)
        return mapping

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
        Redirect.objects.update_or_create(
            from_path=legacy,
            defaults={
                "to_path": to_path,
                "status_code": 301,
                "is_active": True,
            },
        )


def _safe_basename(url: str) -> str:
    """Derive a short WebP filename from a remote URL path."""
    name = Path(urlparse(url).path).name or "image.jpg"
    stem = Path(name).stem[:80] or "image"
    return f"{stem}.webp"
