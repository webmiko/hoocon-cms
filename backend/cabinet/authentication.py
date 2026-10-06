"""DRF authentication for the client cabinet session.

``ClientAccount`` is not a Django ``User`` — the cabinet session stores the
account id in the Django session cookie. This authentication resolves it and
enforces CSRF on cookie-authenticated requests (same rule as staff
``SessionAuthentication``).
"""

from __future__ import annotations

from typing import Any

from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request

from cabinet.auth import load_client_account


class ClientSessionAuthentication(SessionAuthentication):
    """Session-cookie auth for ``/api/account/*`` (client, not staff).

    Returns ``(ClientAccount, None)`` so ``request.user`` is the account;
    CSRF is enforced on all session-authenticated requests exactly like
    DRF's ``SessionAuthentication``.
    """

    def authenticate(self, request: Request) -> tuple[Any, None] | None:
        account = load_client_account(request)
        if account is None:
            return None
        self.enforce_csrf(request)
        return account, None
