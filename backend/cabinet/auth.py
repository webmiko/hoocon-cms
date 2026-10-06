"""Client cabinet session auth (separate from staff ``auth.User``).

Session-based per plan-client-auth §2: after login the ``ClientAccount``
id lives in the Django session cookie — no JWT, no localStorage tokens.
DRF ``authentication_classes`` on account views resolve the account via
:func:`load_client_account`.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from accounts.models import ClientAccount

_SESSION_KEY = "client_account_id"


def login_client(request: HttpRequest, account: ClientAccount) -> None:
    """Attach a client account to the session (rotates the session key)."""
    request.session.cycle_key()
    request.session[_SESSION_KEY] = account.pk


def logout_client(request: HttpRequest) -> None:
    """Drop the client account from the session."""
    request.session.pop(_SESSION_KEY, None)


def load_client_account(request: HttpRequest | Request) -> ClientAccount | None:
    """Resolve the active ClientAccount from the session, if any."""
    raw_request = getattr(request, "_request", request)
    account_id = raw_request.session.get(_SESSION_KEY)
    if not account_id:
        return None
    try:
        account = ClientAccount.objects.get(pk=account_id, is_active=True)
    except ClientAccount.DoesNotExist:
        raw_request.session.pop(_SESSION_KEY, None)
        return None
    return account


class IsClientAccount(BasePermission):
    """DRF permission: request must carry an active client session."""

    def has_permission(self, request: Request, view: Any) -> bool:
        # ClientSessionAuthentication already resolved the account into
        # request.user — reuse it; the session lookup is the fallback.
        if isinstance(request.user, ClientAccount):
            return True
        return load_client_account(request) is not None
