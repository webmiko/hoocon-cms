"""Celery tasks for social announcements."""

from __future__ import annotations

from typing import Any

from celery import shared_task
from django.apps import apps

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.social")


@shared_task(
    bind=True,
    autoretry_for=(OSError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="social.announce_content",
)
def announce_content_task(
    self: Any,
    model_label: str,
    object_id: int,
    *,
    force: bool = False,
) -> dict[str, int]:
    """Load content by label+id and announce to social channels.

    Args:
        self: Celery task (bind=True).
        model_label: ``app_label.model_name`` (e.g. ``content.article``).
        object_id: primary key.
        force: re-send even if already SENT.

    Returns:
        Counts by status for created posts.
    """
    from social.services import announce_content

    try:
        model = apps.get_model(model_label)
    except LookupError:
        logger.error("announce_unknown_model label=%s", model_label)
        return {"error": 1}

    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        logger.error("announce_missing_object label=%s id=%s", model_label, object_id)
        return {"error": 1}

    posts = announce_content(obj, force=force)
    counts: dict[str, int] = {}
    for post in posts:
        counts[post.status] = counts.get(post.status, 0) + 1
    return counts
