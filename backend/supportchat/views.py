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
    chat_faq_items,
    get_web_conversation,
    start_or_resume_web_conversation,
)

logger = setup_logger("hoocon.supportchat")

_MSG_THROTTLE = "support_message"
_POLL_THROTTLE = "support_poll"


def _conversation_public_payload(conversation) -> dict[str, object]:
    """Visitor-facing conversation state for the support widget."""
    return {
        "id": conversation.pk,
        "display_name": conversation.display_name,
        "contact_email": conversation.contact_email,
        "ai_active": bool(conversation.ai_active and conversation.ai_escalated_at is None),
        "ai_escalated": conversation.ai_escalated_at is not None,
    }


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
                # Deep-link opens a 1:1 chat with the bot (not the public channel).
                channels.append(
                    {
                        "channel": "telegram_bot",
                        "provider": "telegram",
                        "kind": "bot",
                        "label": "Написать в Telegram",
                        "deep_link": f"https://t.me/{bot}?start=support",
                    },
                )
            channel = getattr(settings, "TELEGRAM_CHANNEL_USERNAME", "").strip().lstrip("@")
            if channel:
                channels.append(
                    {
                        "channel": "telegram_channel",
                        "provider": "telegram",
                        "kind": "channel",
                        "label": "Канал Telegram",
                        "deep_link": f"https://t.me/{channel}",
                    },
                )
        if site.max_enabled:
            from social.max_bot import max_bot_deep_link, max_channel_deep_link

            channels.append(
                {
                    "channel": "max_bot",
                    "provider": "max",
                    "kind": "bot",
                    "label": "Написать в MAX",
                    "deep_link": max_bot_deep_link("support"),
                },
            )
            channels.append(
                {
                    "channel": "max_channel",
                    "provider": "max",
                    "kind": "channel",
                    "label": "Канал MAX",
                    "deep_link": max_channel_deep_link(),
                },
            )
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
                "ai_active": bool(conv.ai_active and conv.ai_escalated_at is None),
                "ai_escalated": conv.ai_escalated_at is not None,
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
            return Response({"messages": [], "conversation": None})
        after = request.query_params.get("after")
        qs = (
            conv.messages.select_related("author", "conversation", "conversation__assignee")
            .all()
            .order_by("created_at", "id")
        )
        if after and str(after).isdigit():
            qs = qs.filter(id__gt=int(after))
        response = Response(
            {
                "messages": MessageSerializer(qs, many=True).data,
                "conversation": _conversation_public_payload(conv),
            },
        )
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

        chat_action = (serializer.validated_data.get("chat_action") or "").strip()
        raw_payload = {"chat_action": chat_action} if chat_action else None
        try:
            inbound, auto = add_inbound_message(
                conv,
                serializer.validated_data["body"],
                raw_payload=raw_payload,
            )
        except SupportChatError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload: dict[str, object] = {
            "message": MessageSerializer(inbound).data,
        }
        if auto is not None:
            payload["auto_reply"] = MessageSerializer(auto).data
        return Response(payload, status=status.HTTP_201_CREATED)


class SupportFaqView(APIView):
    """GET /api/support/faq/ — FAQ из Admin (публично, scope=chat|home|seo)."""

    permission_classes = (AllowAny,)
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "support_faq"

    def get(self, request: Request) -> Response:
        from supportchat.faq import home_faq_items, seo_faq_tuples

        scope = (request.query_params.get("scope") or "chat").strip().casefold()
        if scope == "home":
            items = home_faq_items()
        elif scope in {"seo", "all"}:
            path = (request.query_params.get("path") or "/faq").strip() or "/faq"
            pairs = seo_faq_tuples(path)
            items = [{"id": index, "question": q, "answer": a} for index, (q, a) in enumerate(pairs, start=1)]
        else:
            items = chat_faq_items()
        response = Response({"items": items, "scope": scope})
        response["Cache-Control"] = "public, max-age=60"
        return response
