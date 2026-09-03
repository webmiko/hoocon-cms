"""Public API: POST /api/analytics/hit/ (essential first-party pageviews)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from analytics.serializers import PageHitSerializer
from analytics.services import record_page_hit

_THROTTLE = "analytics_hit"


class PageHitView(APIView):
    """Record one SPA navigation hit (no marketing consent required).

    Uses the Django session cookie (essential) for unique-visitor counting.
    """

    permission_classes = (AllowAny,)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _THROTTLE
    http_method_names = ["post", "head", "options"]

    def post(self, request: Request) -> Response:
        serializer = PageHitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ok = record_page_hit(
            request=request._request,
            path=str(data.get("path") or ""),
            title=str(data.get("title") or ""),
            object_type=str(data.get("object_type") or ""),
            object_key=str(data.get("object_key") or ""),
        )
        if not ok:
            return Response(
                {"detail": "invalid path"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)
