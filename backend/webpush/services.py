"""Web Push delivery helpers (VAPID + pywebpush)."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.db.models import QuerySet

from webpush.models import PushSubscription

logger = logging.getLogger("hoocon.webpush")


class WebPushConfigError(Exception):
    """VAPID keys missing or invalid."""


def vapid_public_key() -> str:
    """Application Server Key (URL-safe base64) for PushManager.subscribe."""
    return getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "").strip()


def vapid_claims() -> dict[str, str]:
    """VAPID JWT claims (subject mailto:…)."""
    subject = getattr(settings, "WEBPUSH_VAPID_SUBJECT", "").strip()
    if not subject:
        subject = "mailto:noreply@hoocon.ru"
    return {"sub": subject}


def vapid_private_key() -> str:
    key = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "").strip()
    if not key:
        raise WebPushConfigError("WEBPUSH_VAPID_PRIVATE_KEY is empty")
    return key


def webpush_configured() -> bool:
    """True when public + private VAPID keys are set."""
    return bool(vapid_public_key() and getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "").strip())


def upsert_subscription(
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    topic_support: bool = False,
    topic_marketing: bool = False,
    user: Any | None = None,
    session_key: str = "",
) -> PushSubscription:
    """Create or update a subscription; merge topic flags with OR."""
    endpoint = (endpoint or "").strip()
    p256dh = (p256dh or "").strip()
    auth = (auth or "").strip()
    if not endpoint or not p256dh or not auth:
        raise ValueError("endpoint, p256dh and auth are required")
    if not topic_support and not topic_marketing:
        raise ValueError("at least one topic required")

    user_pk = getattr(user, "pk", None) if user is not None else None
    if user_pk is not None and not getattr(user, "is_authenticated", False):
        user_pk = None
        user = None

    existing = PushSubscription.objects.filter(endpoint=endpoint).first()
    if existing is None:
        return PushSubscription.objects.create(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user=user if user_pk else None,
            session_key=(session_key or "")[:64],
            topic_support=topic_support,
            topic_marketing=topic_marketing,
        )

    existing.p256dh = p256dh
    existing.auth = auth
    if user_pk:
        existing.user = user
    if session_key:
        existing.session_key = session_key[:64]
    if topic_support:
        existing.topic_support = True
    if topic_marketing:
        existing.topic_marketing = True
    existing.save()
    return existing


def remove_subscription(endpoint: str) -> int:
    """Delete by endpoint; return number deleted."""
    return PushSubscription.objects.filter(endpoint=(endpoint or "").strip()).delete()[0]


def send_push_to_subscription(
    subscription: PushSubscription,
    *,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "",
) -> bool:
    """Send one notification. Returns False if skipped/gone; deletes on 410."""
    if not webpush_configured():
        logger.warning("webpush_skip_not_configured")
        return False

    from pywebpush import WebPushException, webpush

    payload = json.dumps(
        {
            "title": title[:120],
            "body": body[:240],
            "url": url or "/",
            "tag": tag or "hoocon",
        },
        ensure_ascii=False,
    )
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=payload,
            vapid_private_key=vapid_private_key(),
            vapid_claims=vapid_claims(),
            ttl=86_400,
        )
        subscription.touch()
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in {404, 410}:
            logger.info("webpush_gone endpoint_id=%s", subscription.pk)
            subscription.delete()
            return False
        logger.warning(
            "webpush_failed id=%s status=%s err=%s",
            subscription.pk,
            status,
            type(exc).__name__,
        )
        return False
    except WebPushConfigError:
        return False


def queryset_staff_support() -> QuerySet[PushSubscription]:
    """Staff subscribers for support-chat alerts."""
    return PushSubscription.objects.filter(
        topic_support=True,
        user__isnull=False,
        user__is_staff=True,
        user__is_active=True,
    )


def queryset_session_support(session_key: str) -> QuerySet[PushSubscription]:
    """Visitor support subscribers for a Django session."""
    key = (session_key or "").strip()
    if not key:
        return PushSubscription.objects.none()
    return PushSubscription.objects.filter(topic_support=True, session_key=key)


def queryset_marketing() -> QuerySet[PushSubscription]:
    return PushSubscription.objects.filter(topic_marketing=True)
