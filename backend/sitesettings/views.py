"""Public site settings API (analytics counter IDs only)."""

from __future__ import annotations

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from sitesettings.models import SiteSettings


class PublicSettingsView(APIView):
    """GET /api/settings/public/ — counter IDs for the SPA (no secrets)."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request) -> Response:
        """Return Yandex Metrika / GA4 IDs from SiteSettings with env defaults.

        Args:
            request: unused DRF request.

        Returns:
            JSON with yandex_metrika_id and ga4_measurement_id (may be empty).
        """
        site = SiteSettings.load()
        ym = (site.yandex_metrika_id or "").strip() or settings.YANDEX_METRIKA_ID
        ga = (site.ga4_measurement_id or "").strip() or settings.GA4_MEASUREMENT_ID
        return Response(
            {
                "yandex_metrika_id": ym.strip(),
                "ga4_measurement_id": ga.strip(),
            }
        )
