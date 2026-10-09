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
    """Drop the client account and its support chat; rotate the session key.

    Without this the next visitor on the same browser kept the chat thread
    (and the old session id) of the client who signed out.
    """
    from supportchat.services import SESSION_KEY as SUPPORT_SESSION_KEY

    request.session.pop(_SESSION_KEY, None)
    request.session.pop(SUPPORT_SESSION_KEY, None)
    request.session.cycle_key()


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


def session_owns_email(request: HttpRequest | Request, email: str) -> bool:
    """True when the visitor is signed in with a verified account for ``email``.

    Contact emails typed into public forms are unproven; only this match
    lets a lead or chat appear in that client's cabinet automatically.
    """
    wanted = (email or "").strip().casefold()
    if not wanted:
        return False
    account = load_client_account(request)
    return bool(
        account is not None
        and account.email_verified_at is not None
        and (account.email or "").strip().casefold() == wanted
    )


class IsClientAccount(BasePermission):
    """DRF permission: an active client session with a verified email.

    The CRM card (quotes, orders, documents) is matched by email, so an
    unproven address must never reach ``/api/account/*``.
    """

    message = "Подтвердите эл. почту: войдите по коду из письма."

    def has_permission(self, request: Request, view: Any) -> bool:
        # ClientSessionAuthentication already resolved the account into
        # request.user — reuse it; the session lookup is the fallback.
        account = request.user if isinstance(request.user, ClientAccount) else load_client_account(request)
        if account is None:
            return False
        return account.email_verified_at is not None
