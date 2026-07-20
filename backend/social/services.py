"""Orchestrate social announcements for Article / News."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from django.db import models, transaction

from sitesettings.models import SiteSettings
from social.compose import compose_announcement
from social.models import SocialChannel, SocialPost, SocialPostStatus
from social.publishers import PublishResult, publish_max, publish_telegram, publish_vk

logger = logging.getLogger("hoocon.social")


def _enabled_channels(site: SiteSettings) -> list[SocialChannel]:
    """Return channels enabled in SiteSettings (config only, not tokens)."""
    channels: list[SocialChannel] = []
    if site.telegram_enabled and site.telegram_chat_id.strip():
        channels.append(SocialChannel.TELEGRAM)
    if site.vk_enabled and site.vk_group_id.strip():
        channels.append(SocialChannel.VK)
    if site.max_enabled and site.max_chat_id.strip():
        channels.append(SocialChannel.MAX)
    return channels


def _already_sent(obj: models.Model, channel: SocialChannel) -> bool:
    """True if a successful post already exists for this object/channel."""
    ct = SocialPost.content_type_for(obj)
    return SocialPost.objects.filter(
        content_type=ct,
        object_id=obj.pk,
        channel=channel,
        status=SocialPostStatus.SENT,
    ).exists()


def _dispatch(channel: SocialChannel, site: SiteSettings, text: str) -> PublishResult:
    """Call the publisher for one channel."""
    if channel == SocialChannel.TELEGRAM:
        return publish_telegram(chat_id=site.telegram_chat_id, text=text)
    if channel == SocialChannel.VK:
        return publish_vk(group_id=site.vk_group_id, text=text)
    if channel == SocialChannel.MAX:
        return publish_max(chat_id=site.max_chat_id, text=text)
    return PublishResult(ok=False, error=f"Unknown channel: {channel}")


def announce_content(
    obj: models.Model,
    *,
    channels: Sequence[SocialChannel] | None = None,
    force: bool = False,
) -> list[SocialPost]:
    """Announce content to configured social channels.

    Args:
        obj: Article or News instance (must have pk).
        channels: Optional subset; default = all enabled in SiteSettings.
        force: Re-send even if a SENT post already exists.

    Returns:
        List of SocialPost rows created in this call.
    """
    if obj.pk is None:
        raise ValueError("Content must be saved before announce_content")

    site = SiteSettings.load()
    target = list(channels) if channels is not None else _enabled_channels(site)
    if not target:
        return []

    text = compose_announcement(obj)
    created: list[SocialPost] = []
    ct = SocialPost.content_type_for(obj)

    for channel in target:
        if not force and _already_sent(obj, channel):
            continue
        post = SocialPost.objects.create(
            content_type=ct,
            object_id=obj.pk,
            channel=channel,
            status=SocialPostStatus.PENDING,
            message_preview=text[:2000],
        )
        result = _dispatch(channel, site, text)
        if result.skipped:
            post.mark_skipped(result.error or "skipped")
        elif result.ok:
            post.mark_sent(external_id=result.external_id)
        else:
            post.mark_failed(result.error or "unknown error")
            logger.warning(
                "social_announce_failed channel=%s content=%s#%s",
                channel,
                ct.model,
                obj.pk,
            )
        created.append(post)
    return created


def schedule_announce_on_commit(
    obj: models.Model,
    *,
    force: bool = False,
) -> None:
    """Queue Celery announce after successful DB commit.

    Args:
        obj: saved Article/News.
        force: pass through to the task.
    """
    from social.tasks import announce_content_task

    model_label = f"{obj._meta.app_label}.{obj._meta.model_name}"
    pk = obj.pk

    def _enqueue() -> None:
        announce_content_task.delay(model_label, pk, force=force)

    transaction.on_commit(_enqueue)
