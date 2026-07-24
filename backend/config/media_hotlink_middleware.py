"""Block foreign-site embedding of ``/media/`` via Referer allowlist."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin

from config.media_hotlink import referer_allowed_for_media


class MediaHotlinkMiddleware(MiddlewareMixin):
    """Deny ``/media/`` when Referer host is outside the project allowlist.

    Prod usually serves media from nginx (same check there). This middleware
    covers Django ``static()`` media in DEBUG and any proxied media path.
    """

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        """Return 403 for hotlinked media, otherwise continue.

        Args:
            request: Incoming HTTP request.

        Returns:
            Forbidden response or None to continue the chain.
        """
        if not getattr(settings, "MEDIA_HOTLINK_ENABLED", True):
            return None

        media_url = settings.MEDIA_URL or "/media/"
        path = request.path
        if not path.startswith(media_url):
            return None

        allowed: frozenset[str] = getattr(
            settings,
            "MEDIA_HOTLINK_ALLOWED_HOSTS",
            frozenset(),
        )
        allow_empty = bool(getattr(settings, "MEDIA_HOTLINK_ALLOW_EMPTY_REFERER", True))
        referer = request.META.get("HTTP_REFERER")
        if referer_allowed_for_media(
            referer,
            allowed_hosts=allowed,
            allow_empty=allow_empty,
        ):
            return None

        return HttpResponseForbidden(
            "Hotlinking is not allowed.",
            content_type="text/plain; charset=utf-8",
        )
