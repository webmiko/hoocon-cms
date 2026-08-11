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
    remove_subscription,
    upsert_subscription,
    vapid_public_key,
    webpush_configured,
)

logger = setup_logger("hoocon.webpush")

_THROTTLE = "webpush_subscribe"


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
    """POST /api/webpush/subscribe/ — CSRF + session.

    ``topic_marketing`` must only be sent after cookie marketing consent
    (enforced client-side). ``topic_support`` links visitors via support
    session id (same as web chat Conversation.external_user_id).
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
    """POST /api/webpush/unsubscribe/."""

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
