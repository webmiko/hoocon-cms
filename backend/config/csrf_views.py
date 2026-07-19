"""CSRF token cookie endpoint.

Spec: ПЛАН §6 Iter 4 — F8 (Lead forms + CSRF).
Provides the csrftoken cookie to SPA clients via a GET request so they can
send it back as X-CSRFToken on POST /api/leads/.

Public (AllowAny); returns a minimal JSON. The cookie is set by Django's
CsrfViewMiddleware thanks to @ensure_csrf_cookie.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView


class CsrfTokenView(APIView):
    """GET /api/csrf/ — set the csrftoken cookie and return the token.

    The SPA calls this once on load (or before the first POST) to obtain
    a valid CSRF token. The token is returned in the JSON body and also
    set as the `csrftoken` cookie by the CSRF middleware.
    """

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request: object, *args: object, **kwargs: object) -> JsonResponse:
        """Return JSON {csrfToken} and set the csrftoken cookie.

        Args:
            request: DRF request.

        Returns:
            200 with {"csrfToken": "<token>"}.
        """
        return JsonResponse({"csrfToken": get_token(request)})  # type: ignore[arg-type]
