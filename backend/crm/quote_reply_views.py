"""Public quote reply API. The token is the credential; no cabinet session."""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from crm.quote_reply import QuoteReplyError, accept_quote, load_reply_quote, reply_preview, revise_quote


class QuoteReplyView(APIView):
    """GET shows the offer. POST accepts it or stores a change request."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "quote_reply"

    def get(self, request: Request) -> Response:
        header = str(request.headers.get("X-Quote-Token") or "")
        query = str(request.query_params.get("token") or "")
        quote = load_reply_quote(header or query)
        if quote is None:
            return Response({"detail": "Ссылка недействительна."}, status=404)
        return Response(reply_preview(quote))

    def post(self, request: Request) -> Response:
        incoming = request.data
        if not isinstance(incoming, dict):
            return Response({"detail": "Неизвестное действие."}, status=400)
        token = str(incoming.get("token") or "")
        action = str(incoming.get("action") or "")
        try:
            if action == "accept":
                payload = accept_quote(token)
            elif action == "revise":
                payload = revise_quote(token, str(incoming.get("comment") or ""))
            else:
                return Response({"detail": "Неизвестное действие."}, status=400)
        except QuoteReplyError as exc:
            return Response({"detail": exc.message}, status=exc.status)
        return Response(payload)
