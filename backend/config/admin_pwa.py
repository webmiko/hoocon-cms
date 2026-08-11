"""Admin-only PWA web app manifest (distinct icons from the public site)."""

from __future__ import annotations

from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import HttpRequest, JsonResponse
from django.views import View


class AdminPwaManifestView(View):
    """GET /admin/manifest.webmanifest — installable Admin shell."""

    http_method_names = ("get", "head")

    def get(self, request: HttpRequest) -> JsonResponse:
        del request
        icon_192 = staticfiles_storage.url("admin/img/pwa-admin-192.png")
        icon_512 = staticfiles_storage.url("admin/img/pwa-admin-512.png")
        icon_maskable = staticfiles_storage.url("admin/img/pwa-admin-512-maskable.png")
        payload = {
            "name": "Hoocon Admin",
            "short_name": "Admin",
            "description": "Панель управления Hoocon CMS",
            "start_url": "/admin/",
            "scope": "/admin/",
            "display": "standalone",
            "background_color": "#5a626c",
            "theme_color": "#5a626c",
            "lang": "ru",
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
