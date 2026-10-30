"""Backfill VK + MAX announces for published article-news that have covers."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from content.models import News
from social.compose import content_cover_path
from social.models import SocialChannel, SocialPost, SocialPostStatus
from social.services import announce_content


class Command(BaseCommand):
    help = (
        "Announce published news with slug prefix (default article-) to VK and MAX "
        "when a cover file exists; skips channels already SENT unless --force."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--slug-prefix",
            default="article-",
            help="Only news whose slug starts with this prefix (default: article-).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List matching news without posting.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-post even when a SENT SocialPost already exists.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        prefix = str(options["slug_prefix"] or "").strip()
        dry_run = bool(options["dry_run"])
        force = bool(options["force"])
        channels = [SocialChannel.VK, SocialChannel.MAX]

        qs = News.objects.filter(is_published=True).order_by("published_at", "pk")
        if prefix:
            qs = qs.filter(slug__startswith=prefix)

        total = 0
        posted = 0
        for news in qs:
            if content_cover_path(news) is None:
                continue
            total += 1
            if not force and self._all_channels_sent(news, channels):
                self.stdout.write(f"skip pk={news.pk} slug={news.slug} (already sent)")
                continue
            if dry_run:
                self.stdout.write(f"would announce pk={news.pk} slug={news.slug}")
                continue
            posts = announce_content(news, channels=channels, force=force)
            posted += len(posts)
            for post in posts:
                self.stdout.write(
                    f"pk={news.pk} {post.channel} {post.status} id={post.external_id or '-'}",
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"done: {total} with cover, {posted} posts created this run",
            ),
        )

    @staticmethod
    def _all_channels_sent(news: News, channels: list[SocialChannel]) -> bool:
        ct = SocialPost.content_type_for(news)
        for channel in channels:
            if not SocialPost.objects.filter(
                content_type=ct,
                object_id=news.pk,
                channel=channel,
                status=SocialPostStatus.SENT,
            ).exists():
                return False
        return True
