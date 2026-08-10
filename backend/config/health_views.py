"""Health check API endpoint.

Spec: ПЛАН §6 Iter 1 — /api/health/ for smoke and k8s-style probes.
No auth; safe payload (status, version, channel, db). No secrets/PII.
"""

from __future__ import annotations

from django.db import connection
from django.http import JsonResponse
from django.views import View

from config.release import RELEASE_CHANNEL, RELEASE_VERSION


class HealthView(View):
    """GET /api/health/ — liveness + readiness probe."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: object, *args: object, **kwargs: object) -> JsonResponse:
        """Return JSON {status, version, channel, db}."""
        db_ok = self._check_db()
        payload = {
            "status": "ok" if db_ok else "degraded",
            "version": RELEASE_VERSION,
            "channel": RELEASE_CHANNEL,
            "db": "ok" if db_ok else "fail",
        }
        status_code = 200 if db_ok else 503
        return JsonResponse(payload, status=status_code)

    @staticmethod
    def _check_db() -> bool:
        """Run a trivial query to verify DB connectivity."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
            return bool(row and row[0] == 1)
        except Exception:  # noqa: BLE001 — health probe must not crash
            return False
