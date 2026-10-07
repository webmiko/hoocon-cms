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

from crm.telephony import handle_mango_event, verify_mango_signature

logger = logging.getLogger("hoocon.crm")


class MangoEventsView(APIView):
    """Inbound Mango events: call state transitions + recording readiness."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mango_webhook"

    def post(self, request: Request) -> Response:
        """Verify signature, decode ``json``, route the event."""
        api_key = str(request.data.get("vpbx_api_key") or "")
        sign = str(request.data.get("sign") or "")
        raw_json = str(request.data.get("json") or "")

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
