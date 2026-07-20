"""Middleware that applies active Redirect rows before the view layer."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin

from redirects.models import Redirect
from redirects.pathutils import normalize_path

# Paths that never participate in SEO redirects (avoid DB on every hit / bare tests).
_SKIP_PREFIXES: tuple[str, ...] = ("/admin", "/api", "/static", "/media")
_SKIP_EXACT: frozenset[str] = frozenset(
    {
        "/robots.txt",
        "/sitemap.xml",
        "/llms.txt",
        "/llm.txt",
        "/llms-full.txt",
        "/favicon.ico",
        "/favicon.svg",
        "/manifest.webmanifest",
    }
)


class RedirectMiddleware(MiddlewareMixin):
    """Look up ``request.path`` in Redirect and return 301/302 when active.

    Open redirects are prevented at import/validation: ``to_path`` must be an
    internal absolute path (see ``redirects.pathutils``).
    """

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        """Return a redirect response when an active mapping exists.

        Args:
            request: Incoming HTTP request.

        Returns:
            Redirect response or ``None`` to continue the chain.
        """
        path = normalize_path(request.path)
        if path in _SKIP_EXACT or path.startswith(_SKIP_PREFIXES):
            return None

        try:
            match = Redirect.objects.filter(from_path=path, is_active=True).only("to_path", "status_code").first()
        except RuntimeError:
            # pytest-django blocks DB outside django_db tests; skip redirects.
            return None

        if match is None:
            return None

        if match.status_code == Redirect.HTTP_MOVED_PERMANENTLY:
            return HttpResponsePermanentRedirect(match.to_path)
        return HttpResponseRedirect(match.to_path)
