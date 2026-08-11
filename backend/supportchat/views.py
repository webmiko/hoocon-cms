"""Public API for the site support widget."""

from __future__ import annotations

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from config.logging_utils import setup_logger
from sitesettings.models import SiteSettings
from supportchat.schedule import schedule_public_payload
from supportchat.serializers import (
    ConversationStartSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from supportchat.services import (
    SupportChatError,
    add_inbound_message,
    get_web_conversation,
    start_or_resume_web_conversation,
)

logger = setup_logger("hoocon.supportchat")

_MSG_THROTTLE = "support_message"
_POLL_THROTTLE = "support_poll"


class SupportScheduleView(APIView):
    """GET /api/support/schedule/ — open hours (public)."""

    permission_classes = (AllowAny,)
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        del request
        return Response(schedule_public_payload())


class SupportChannelsView(APIView):
    """GET /api/support/channels/ — enabled messengers + deep links (no tokens)."""

    permission_classes = (AllowAny,)
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        del request
        site = SiteSettings.load()
        channels: list[dict[str, str]] = []
        if site.telegram_enabled:
            bot = getattr(settings, "TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
            if bot:
                channels.append(
                    {
                        "channel": "telegram_bot",
                        "label": "Чат в Telegram",
                        "deep_link": f"https://t.me/{bot}",
                    },
                )
            channel = getattr(settings, "TELEGRAM_CHANNEL_USERNAME", "").strip().lstrip("@")
            if channel:
                channels.append(
                    {
                        "channel": "telegram_channel",
                        "label": "Канал Telegram",
                        "deep_link": f"https://t.me/{channel}",
                    },
                )
        # VK / MAX: only when enabled + we have a public deep link later.
        return Response({"channels": channels})


class ConversationStartView(APIView):
    """POST /api/support/conversations/ — start or resume web session thread."""

    permission_classes = (AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _MSG_THROTTLE

    def post(self, request: Request) -> Response:
        serializer = ConversationStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("website"):
            logger.info("support_honeypot_hit action=start")
            return Response(
                {"id": None, "channel": "web"},
                status=status.HTTP_201_CREATED,
            )
        conv = start_or_resume_web_conversation(
            request._request,
            display_name=serializer.validated_data.get("display_name", ""),
            contact_email=serializer.validated_data.get("contact_email", ""),
        )
        return Response(
            {
                "id": conv.pk,
                "channel": conv.channel,
                "display_name": conv.display_name,
                "contact_email": conv.contact_email,
            },
            status=status.HTTP_201_CREATED,
        )


class CurrentMessagesView(APIView):
    """GET/POST /api/support/conversations/current/messages/."""

    permission_classes = (AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    # Default for POST; GET overrides via get_throttles().
    throttle_scope = _MSG_THROTTLE

    def get_throttles(self) -> list:
        """Poll GETs use a higher rate than POST send/start."""
        if self.request.method == "GET":
            self.throttle_scope = _POLL_THROTTLE
        else:
            self.throttle_scope = _MSG_THROTTLE
        return super().get_throttles()

    def get(self, request: Request) -> Response:
        conv = get_web_conversation(request._request)
        if conv is None:
            return Response({"messages": []})
        after = request.query_params.get("after")
        qs = (
            conv.messages.select_related("author", "conversation", "conversation__assignee")
            .all()
            .order_by("created_at", "id")
        )
        if after and str(after).isdigit():
            qs = qs.filter(id__gt=int(after))
        response = Response({"messages": MessageSerializer(qs, many=True).data})
        # Polling must never be served stale from browser/proxy caches.
        response["Cache-Control"] = "no-store"
        return response

    def post(self, request: Request) -> Response:
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("website"):
            logger.info("support_honeypot_hit action=message")
            return Response({"id": None}, status=status.HTTP_201_CREATED)

        conv = get_web_conversation(request._request)
        if conv is None:
            conv = start_or_resume_web_conversation(request._request)

        try:
            inbound, auto = add_inbound_message(
                conv,
                serializer.validated_data["body"],
            )
        except SupportChatError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload: dict[str, object] = {
            "message": MessageSerializer(inbound).data,
        }
        if auto is not None:
            payload["auto_reply"] = MessageSerializer(auto).data
        return Response(payload, status=status.HTTP_201_CREATED)
