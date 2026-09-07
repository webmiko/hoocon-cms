"""Admin-only PWA web app manifest (distinct icons from the public site)."""

from __future__ import annotations

from pathlib import Path

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View

from config.static_urls import versioned_static

_ADMIN_SW = Path(__file__).resolve().parent.parent / "static" / "admin" / "js" / "hoocon-admin-sw.js"


class AdminPwaManifestView(View):
    """GET /admin/manifest.webmanifest — installable Admin shell."""

    http_method_names = ("get", "head")

    def get(self, request: HttpRequest) -> JsonResponse:
        del request
        icon_192 = versioned_static("admin/img/pwa-admin-192.png")
        icon_512 = versioned_static("admin/img/pwa-admin-512.png")
        icon_maskable = versioned_static("admin/img/pwa-admin-512-maskable.png")
        payload = {
            "name": "Hoocon Admin",
            "short_name": "Admin",
            "description": "Панель управления Hoocon CMS",
            "start_url": "/admin/",
            "scope": "/admin/",
            "display": "standalone",
            "display_override": ["standalone", "minimal-ui"],
            "background_color": "#5a626c",
            "theme_color": "#5a626c",
            "lang": "ru",
            "orientation": "portrait-primary",
            "icons": [
                {
                    "src": icon_192,
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": icon_512,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": icon_maskable,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
            ],
        }
        response = JsonResponse(payload)
        response["Content-Type"] = "application/manifest+json; charset=utf-8"
        response["Cache-Control"] = "public, max-age=3600"
        return response


class AdminPwaServiceWorkerView(View):
    """GET /admin/sw.js — Admin-scoped Web Push service worker."""

    http_method_names = ("get", "head")

    def get(self, request: HttpRequest) -> HttpResponse:
        del request
        body = _ADMIN_SW.read_text(encoding="utf-8") if _ADMIN_SW.is_file() else ""
        response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Service-Worker-Allowed"] = "/admin/"
        return response
