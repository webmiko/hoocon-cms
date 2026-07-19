"""Content-Security-Policy middleware for Hoocon CMS.

Spec: ПЛАН §6 Iter 4 — F10 (CSP draft); docs/security-baseline.md §CSP;
БЗ SEO — nonce for JSON-LD in spa_index HTML; Metrika/GA after consent.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


def build_csp(*, nonce: str | None = None) -> str:
    """Build CSP directive string.

    Args:
        nonce: Per-request nonce for SPA HTML (JSON-LD / inline).

    Returns:
        Full Content-Security-Policy value.
    """
    script_parts = ["'self'"]
    if nonce:
        script_parts.insert(0, f"'nonce-{nonce}'")
    connect_parts = ["'self'"]
    img_parts = ["'self'", "data:"]

    if getattr(settings, "YANDEX_METRIKA_ID", ""):
        script_parts.extend(["https://mc.yandex.ru", "https://mc.yandex.com"])
        connect_parts.extend(["https://mc.yandex.ru", "https://mc.yandex.com"])
        img_parts.append("https://mc.yandex.ru")

    if getattr(settings, "GA4_MEASUREMENT_ID", ""):
        script_parts.append("https://www.googletagmanager.com")
        connect_parts.extend(
            [
                "https://www.google-analytics.com",
                "https://www.googletagmanager.com",
            ]
        )
        img_parts.append("https://www.google-analytics.com")

    directives = [
        "default-src 'self'",
        f"script-src {' '.join(script_parts)}",
        "style-src 'self' 'unsafe-inline'",
        f"img-src {' '.join(img_parts)}",
        "font-src 'self' data:",
        f"connect-src {' '.join(connect_parts)}",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
    return "; ".join(directives)


class CspMiddleware:
    """Sets Content-Security-Policy; attaches request.csp_nonce for SPA."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Init middleware with the next handler in the chain.

        Args:
            get_response: callable that returns an HttpResponse.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request and add CSP headers to the response.

        Args:
            request: incoming HttpRequest.

        Returns:
            HttpResponse with Content-Security-Policy header set.
        """
        request.csp_nonce = secrets.token_urlsafe(16)  # type: ignore[attr-defined]
        response = self.get_response(request)
        self._add_csp_header(request, response)
        return response

    @staticmethod
    def _add_csp_header(request: HttpRequest, response: HttpResponse) -> None:
        """Add the CSP header (Report-Only in DEBUG).

        Args:
            request: request carrying optional csp_nonce.
            response: the HttpResponse to modify.
        """
        nonce = getattr(request, "csp_nonce", None)
        # Nonce only for HTML SPA shells — API JSON does not need it.
        content_type = response.get("Content-Type", "")
        use_nonce = nonce if "text/html" in content_type else None
        value = build_csp(nonce=use_nonce)
        if getattr(settings, "DEBUG", False):
            response.headers["Content-Security-Policy-Report-Only"] = value
        else:
            response.headers["Content-Security-Policy"] = value
