"""Staff API bearer token hashing and issuance."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from staff_api.models import StaffAuthToken, generate_staff_token

_LAST_USED_TOUCH_INTERVAL = timedelta(minutes=5)


def hash_staff_token(raw: str) -> str:
    """Hash opaque token for storage (SECRET_KEY pepper, staff-specific tag)."""
    pepper = str(settings.SECRET_KEY).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(pepper)
    digest.update(b"|staff-api-token|")
    digest.update(raw.encode("utf-8"))
    return digest.hexdigest()


def staff_token_ttl() -> timedelta:
    """Lifetime for newly issued staff API tokens."""
    days = int(getattr(settings, "STAFF_API_TOKEN_TTL_DAYS", 90))
    return timedelta(days=max(days, 1))


def issue_staff_token(user: object) -> str:
    """Create a hashed token row and return the plaintext bearer secret once."""
    raw = generate_staff_token()
    StaffAuthToken.objects.create(
        user=user,
        key=hash_staff_token(raw),
        expires_at=timezone.now() + staff_token_ttl(),
    )
    return raw


def touch_staff_token_last_used(token: StaffAuthToken) -> None:
    """Update ``last_used_at`` at most once per interval (audit: write churn)."""
    now = timezone.now()
    if token.last_used_at and token.last_used_at > now - _LAST_USED_TOUCH_INTERVAL:
        return
    StaffAuthToken.objects.filter(pk=token.pk).update(last_used_at=now)
    token.last_used_at = now


def lookup_staff_token(raw: str) -> StaffAuthToken | None:
    """Resolve bearer secret to a token row, or None when missing/expired."""
    try:
        token = StaffAuthToken.objects.select_related("user").get(key=hash_staff_token(raw))
    except StaffAuthToken.DoesNotExist:
        return None
    if token.expires_at and token.expires_at <= timezone.now():
        token.delete()
        return None
    return token
