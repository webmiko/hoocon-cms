"""Public site settings API (analytics counter IDs only)."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sitesettings.models import SiteSettings


class PublicSettingsView(APIView):
    """GET /api/settings/public/ — counter IDs for the SPA (no secrets)."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request) -> Response:
        """Return Yandex Metrika / GA4 IDs from SiteSettings.

        Args:
            request: unused DRF request.

        Returns:
            JSON with yandex_metrika_id and ga4_measurement_id (may be empty).
        """
        site = SiteSettings.load()
        return Response(
            {
                "yandex_metrika_id": site.yandex_metrika_id.strip(),
                "ga4_measurement_id": site.ga4_measurement_id.strip(),
            }
        )
