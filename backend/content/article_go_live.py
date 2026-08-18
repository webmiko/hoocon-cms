"""Go-live for scheduled articles: news + social announce.

When ``published_at`` is due, a beat task creates a short News item and
announces it (Telegram / VK / MAX) if ``social_announce_on_publish`` is on.
Idempotent: news slug ``article-<article.slug>``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.text import Truncator

from config.logging_utils import setup_logger
from content.models import Article, News
from content.news_categories import CATEGORY_STATI, ensure_categories

logger = setup_logger("hoocon.content.go_live")

# Selection-guide articles that get a dedicated go-live news (not the ones
# already covered by ``articles-podbor-i-sertifikaty``).
AUTO_GO_LIVE_NEWS_SLUGS: frozenset[str] = frozenset(
    {
        "tipy-upravleniya-privodom",
        "pitanie-24-ili-230-v",
        "mu-mqu-hv-kogda-nuzhen-uskorennyy",
        "analog-belimo-hoocon",
    }
)

_NEWS_SLUG_PREFIX = "article-"


@dataclass(frozen=True)
class GoLiveResult:
    """Outcome of processing one due article."""

    article_slug: str
    news_slug: str
    news_created: bool
    announced: int


def go_live_news_slug(article_slug: str) -> str:
    """Stable news slug for an article go-live announcement."""
    return f"{_NEWS_SLUG_PREFIX}{article_slug}"[:300]


def _news_title(article: Article) -> str:
    """Human title for the go-live news."""
    return Truncator(f"Новая статья: {article.title}").chars(300)


def _news_body(article: Article) -> str:
    """Short HTML body linking to the article."""
    path = f"/statyi/{article.slug}"
    excerpt = (article.excerpt or "").strip()
    parts = [
        '<p>В разделе <a href="/statyi">«Статьи»</a> опубликовано:</p>',
        f'<p><strong><a href="{path}">{article.title}</a></strong></p>',
    ]
    if excerpt:
        parts.append(f"<p>{excerpt}</p>")
    parts.append(f'<p><a href="{path}">Читать статью</a></p>')
    return "\n".join(parts)


def _copy_cover(news: News, article: Article) -> None:
    """Copy light cover from article to news when news has none."""
    if news.cover or not article.cover:
        return
    try:
        with article.cover.open("rb") as handle:
            payload = handle.read()
    except OSError:
        logger.warning("go_live_cover_read_failed article=%s", article.slug)
        return
    if not payload:
        return
    basename = article.cover.name.rsplit("/", 1)[-1] or "cover.webp"
    news.cover.save(basename, ContentFile(payload), save=True)


def ensure_go_live_news(article: Article) -> tuple[News, bool]:
    """Create or return the go-live news for ``article``.

    Returns:
        (news, created).
    """
    slug = go_live_news_slug(article.slug)
    existing = News.objects.filter(slug=slug).first()
    if existing is not None:
        return existing, False

    now = timezone.now()
    cats = ensure_categories()
    news = News(
        slug=slug,
        title=_news_title(article),
        body=_news_body(article),
        is_published=True,
        published_at=now,
        category=cats.get(CATEGORY_STATI),
    )
    news.save()
    _copy_cover(news, article)
    return news, True


def process_due_article(article: Article, *, announce: bool = True) -> GoLiveResult:
    """Ensure go-live news exists and optionally announce to social."""
    news, created = ensure_go_live_news(article)
    announced = 0
    if announce:
        from sitesettings.models import SiteSettings
        from social.services import announce_content

        site = SiteSettings.load()
        if site.social_announce_on_publish:
            posts = announce_content(news, force=False)
            announced = len(posts)
        else:
            logger.info(
                "go_live_skip_announce slug=%s (social_announce_on_publish=off)",
                article.slug,
            )
    return GoLiveResult(
        article_slug=article.slug,
        news_slug=news.slug,
        news_created=created,
        announced=announced,
    )


def _pending_go_live_slugs() -> frozenset[str]:
    """AUTO_GO_LIVE slugs that do not yet have ``article-<slug>`` news."""
    news_to_article = {go_live_news_slug(slug): slug for slug in AUTO_GO_LIVE_NEWS_SLUGS}
    taken = set(
        News.objects.filter(slug__in=news_to_article).values_list("slug", flat=True),
    )
    return frozenset(slug for news_slug, slug in news_to_article.items() if news_slug not in taken)


def publish_due_articles(*, announce: bool = True) -> list[GoLiveResult]:
    """Process AUTO_GO_LIVE articles whose ``published_at`` is due.

    Skips slugs that already have go-live news so a later beat can pick the
    next scheduled guide. At most one article per run (social rate-limit).
    Oldest due ``published_at`` first.

    Returns:
        One result per processed article (created and/or announced).
    """
    now = timezone.now()
    pending = _pending_go_live_slugs()
    if not pending:
        return []
    due = Article.objects.filter(
        slug__in=pending,
        is_published=True,
        published_at__isnull=False,
        published_at__lte=now,
    ).order_by("published_at", "id")[:1]
    results: list[GoLiveResult] = []
    for article in due:
        with transaction.atomic():
            result = process_due_article(article, announce=announce)
        if result.news_created or result.announced:
            logger.info(
                "go_live article=%s news=%s created=%s announced=%s",
                result.article_slug,
                result.news_slug,
                result.news_created,
                result.announced,
            )
            results.append(result)
    return results
