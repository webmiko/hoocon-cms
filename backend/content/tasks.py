"""Celery tasks for CMS content go-live."""

from __future__ import annotations

from celery import shared_task

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.content.tasks")


@shared_task(name="content.publish_due_articles")
def publish_due_articles_task() -> dict[str, int]:
    """Create go-live news for due scheduled articles and announce.

    Returns:
        Counters: processed, news_created, announced.
    """
    from content.article_go_live import publish_due_articles

    results = publish_due_articles(announce=True)
    news_created = sum(1 for r in results if r.news_created)
    announced = sum(r.announced for r in results)
    logger.info(
        "publish_due_articles processed=%s news_created=%s announced=%s",
        len(results),
        news_created,
        announced,
    )
    return {
        "processed": len(results),
        "news_created": news_created,
        "announced": announced,
    }
