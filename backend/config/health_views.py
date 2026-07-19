"""Health check API endpoint.

Spec: ПЛАН §6 Iter 1 — /api/health/ for smoke and k8s-style probes.
No auth; safe payload (status, version, db). No secrets/PII.
"""

from __future__ import annotations

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views import View


class HealthView(View):
    """GET /api/health/ — liveness + readiness probe."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: object, *args: object, **kwargs: object) -> JsonResponse:
        """Return JSON {status, version, db}."""
        db_ok = self._check_db()
        payload = {
            "status": "ok" if db_ok else "degraded",
            "version": self._app_version(),
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

    @staticmethod
    def _app_version() -> str:
        """Return the app version from SPECTACULAR_SETTINGS or '0.0.0'."""
        spectacular = getattr(settings, "SPECTACULAR_SETTINGS", {})
        return str(spectacular.get("VERSION", "0.0.0"))
