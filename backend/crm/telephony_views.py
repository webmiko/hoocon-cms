"""Webhook endpoints for Mango VPBX events.

``POST /api/telephony/mango/events/`` — Mango шлёт form-POST
``vpbx_api_key``, ``json``, ``sign``; подпись проверяется по
``sha256(key + json + salt)``. Обработка синхронная — события лёгкие,
Mango ждёт быстрый 200.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from crm.novosystem import handle_novosystem_event, webhook_token_ok
from crm.telephony import handle_mango_event, verify_mango_signature

logger = logging.getLogger("hoocon.crm")


class MangoEventsView(APIView):
    """Inbound Mango events: call state transitions + recording readiness."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mango_webhook"

    def post(self, request: Request, kind: str = "") -> Response:
        """Verify signature, decode ``json``, route the event."""
        data = request.data
        if not isinstance(data, dict):
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)
        api_key = str(data.get("vpbx_api_key") or "")
        sign = str(data.get("sign") or "")
        raw_json = str(data.get("json") or "")

        if not verify_mango_signature(api_key, raw_json, sign):
            logger.warning("mango_event_bad_signature")
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        try:
            payload = json.loads(raw_json)
        except ValueError:
            logger.warning("mango_event_bad_json")
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)

        verdict = handle_mango_event(payload)
        return Response({"ok": True, "verdict": verdict}, status=status.HTTP_200_OK)


class NovosystemEventsView(APIView):
    """Inbound UIS webhook. Secret must match the telephony widget."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "novosystem_webhook"

    def post(self, request: Request) -> Response:
        """Accept JSON or form body when ``token`` matches the widget secret."""
        return self._accept(request)

    def get(self, request: Request) -> Response:
        """UIS can send the same notification as GET."""
        return self._accept(request)

    def _accept(self, request: Request) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        query = request.query_params
        token = str(data.get("token") or query.get("token") or request.headers.get("X-Webhook-Token") or "")
        if not webhook_token_ok(token):
            logger.warning("novosystem_event_rejected")
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)
        payload = {
            key: data.get(key, query.get(key))
            for key in (
                "call_session_id",
                "id",
                "direction",
                "contact_phone_number",
                "calling_phone_number",
                "virtual_phone_number",
                "extension",
                "employee_id",
                "start_time",
                "talk_duration",
                "talk_time_duration",
                "is_lost",
                "finish_time",
                "recording_id",
                "call_records",
            )
        }
        verdict = handle_novosystem_event(payload)
        if verdict == "ignored":
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "verdict": verdict}, status=status.HTTP_200_OK)
