"""Admin-only PWA web app manifest (distinct icons from the public site)."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views import View

from config.static_urls import versioned_static


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
