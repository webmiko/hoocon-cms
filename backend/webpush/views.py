"""Public API for Web Push subscribe / unsubscribe / VAPID key."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from config.logging_utils import setup_logger
from webpush.services import (
    clear_subscription_topics,
    remove_subscription,
    upsert_subscription,
    vapid_public_key,
    webpush_configured,
)

logger = setup_logger("hoocon.webpush")

_THROTTLE = "webpush_subscribe"
_SESSION_MARKETING_CONSENT = "hoocon_marketing_push_consent"
_MARKETING_CONSENT_HEADER = "HTTP_X_HOOCON_MARKETING_CONSENT"


def _header_marketing_consent(request: Request) -> bool:
    raw = str(request.META.get(_MARKETING_CONSENT_HEADER) or "").strip().lower()
    return raw in {"1", "true", "yes"}


def _session_marketing_consent(request: Request) -> bool:
    django_req = request._request
    return bool(django_req.session.get(_SESSION_MARKETING_CONSENT))


def _set_session_marketing_consent(request: Request, allowed: bool) -> None:
    django_req = request._request
    django_req.session[_SESSION_MARKETING_CONSENT] = bool(allowed)
    django_req.session.modified = True


def _marketing_consent_ok(request: Request) -> bool:
    """True when session opt-in is set, or header echoes cookie and we persist it."""
    if _session_marketing_consent(request):
        return True
    if _header_marketing_consent(request):
        _set_session_marketing_consent(request, True)
        return True
    return False


class VapidPublicKeyView(APIView):
    """GET /api/webpush/vapid-public-key/."""

    permission_classes = (AllowAny,)
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        del request
        if not webpush_configured():
            return Response({"public_key": "", "configured": False})
        return Response({"public_key": vapid_public_key(), "configured": True})


class SubscribeView(APIView):
    """POST /api/webpush/subscribe/ — session-bound.

    ``topic_marketing`` requires marketing consent in Django session
    (set via ``X-Hoocon-Marketing-Consent: 1`` echo of cookie opt-in, or
    prior ``/topics/`` consent sync). ``topic_support`` links visitors via
    support session id.
    """

    permission_classes = (AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _THROTTLE

    def post(self, request: Request) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        endpoint = str(data.get("endpoint") or "").strip()
        keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
        p256dh = str(keys.get("p256dh") or data.get("p256dh") or "").strip()
        auth = str(keys.get("auth") or data.get("auth") or "").strip()
        topic_support = bool(data.get("topic_support"))
        topic_marketing = bool(data.get("topic_marketing"))
        if topic_marketing and not _marketing_consent_ok(request):
            return Response(
                {"detail": "marketing consent required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user if getattr(request.user, "is_authenticated", False) else None
        session_key = ""
        django_req = request._request
        if topic_support and not (user and getattr(user, "is_staff", False)):
            from supportchat.services import get_or_create_web_session_id

            session_key = get_or_create_web_session_id(django_req)

        try:
            sub = upsert_subscription(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                topic_support=topic_support,
                topic_marketing=topic_marketing,
                user=user,
                session_key=session_key,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": sub.pk,
                "topic_support": sub.topic_support,
                "topic_marketing": sub.topic_marketing,
            },
            status=status.HTTP_201_CREATED,
        )


class UnsubscribeView(APIView):
    """POST /api/webpush/unsubscribe/ — delete whole endpoint."""

    permission_classes = (AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _THROTTLE

    def post(self, request: Request) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        endpoint = str(data.get("endpoint") or "").strip()
        if not endpoint:
            return Response({"detail": "endpoint required"}, status=status.HTTP_400_BAD_REQUEST)
        deleted = remove_subscription(endpoint)
        return Response({"deleted": deleted})


class TopicsView(APIView):
    """POST /api/webpush/topics/ — clear topics and/or sync marketing consent.

    Body examples::

        {"endpoint": "…", "clear_marketing": true}
        {"marketing_consent": false}
        {"endpoint": "…", "clear_support": true, "marketing_consent": false}
    """

    permission_classes = (AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _THROTTLE

    def post(self, request: Request) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        if "marketing_consent" in data:
            allowed = bool(data.get("marketing_consent"))
            _set_session_marketing_consent(request, allowed)
            if not allowed:
                # Revoking cookie marketing also clears session gate for subscribe.
                pass

        endpoint = str(data.get("endpoint") or "").strip()
        clear_support = bool(data.get("clear_support"))
        clear_marketing = bool(data.get("clear_marketing"))
        if not endpoint:
            if "marketing_consent" in data:
                return Response(
                    {
                        "marketing_consent": _session_marketing_consent(request),
                    },
                )
            return Response(
                {"detail": "endpoint required to clear topics"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not clear_support and not clear_marketing:
            if "marketing_consent" in data:
                return Response(
                    {
                        "endpoint": endpoint,
                        "marketing_consent": _session_marketing_consent(request),
                    },
                )
            return Response(
                {"detail": "clear_support and/or clear_marketing required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sub = clear_subscription_topics(
                endpoint,
                clear_support=clear_support,
                clear_marketing=clear_marketing,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if sub is None:
            return Response(
                {
                    "deleted": True,
                    "topic_support": False,
                    "topic_marketing": False,
                    "marketing_consent": _session_marketing_consent(request),
                },
            )
        return Response(
            {
                "deleted": False,
                "topic_support": sub.topic_support,
                "topic_marketing": sub.topic_marketing,
                "marketing_consent": _session_marketing_consent(request),
            },
        )
