"""WebAuthn passkey helpers for Admin passwordless login."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from accounts.models import PasskeyCredential

logger = logging.getLogger(__name__)

User = get_user_model()

_SESSION_REG_CHALLENGE = "admin_passkey_reg_challenge"
_SESSION_REG_USER = "admin_passkey_reg_user_id"
_SESSION_REG_EXPIRES = "admin_passkey_reg_expires"
_SESSION_AUTH_CHALLENGE = "admin_passkey_auth_challenge"
_SESSION_AUTH_EXPIRES = "admin_passkey_auth_expires"
_SESSION_AUTH_NEXT = "admin_passkey_auth_next"


def admin_passkey_enabled() -> bool:
    """True when Admin WebAuthn passkeys are turned on."""
    return bool(getattr(settings, "ADMIN_PASSKEY_ENABLED", False))


def passkey_rp_id() -> str:
    """Relying Party ID (hostname)."""
    return str(getattr(settings, "ADMIN_PASSKEY_RP_ID", "localhost")).strip()


def passkey_rp_name() -> str:
    """Human-readable RP name shown in OS prompts."""
    return str(getattr(settings, "ADMIN_PASSKEY_RP_NAME", "HOOCON CMS")).strip()


def passkey_origin() -> str:
    """Expected origin (scheme + host[+port]), no trailing slash."""
    return str(getattr(settings, "ADMIN_PASSKEY_ORIGIN", "http://localhost:8000")).rstrip("/")


def challenge_ttl_seconds() -> int:
    """Challenge lifetime in seconds."""
    return int(getattr(settings, "ADMIN_PASSKEY_CHALLENGE_TTL_SECONDS", 300))


def _user_handle(user: Any) -> bytes:
    """Stable WebAuthn user.id bytes from PK."""
    return int(user.pk).to_bytes(8, "big", signed=False)


def _webauthn_user_name(user: Any) -> str:
    email = (getattr(user, "email", "") or "").strip()
    if email:
        return email
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        return str(get_username() or user.pk)
    return str(user.pk)


def _webauthn_display_name(user: Any) -> str:
    get_full_name = getattr(user, "get_full_name", None)
    if callable(get_full_name):
        full = (get_full_name() or "").strip()
        if full:
            return full
    return _webauthn_user_name(user)


def _exclude_credentials(user: Any) -> list[PublicKeyCredentialDescriptor]:
    from webauthn.helpers import base64url_to_bytes

    out: list[PublicKeyCredentialDescriptor] = []
    for cred in PasskeyCredential.objects.filter(user_id=user.pk).only("credential_id"):
        try:
            out.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred.credential_id)),
            )
        except Exception:  # noqa: BLE001 — skip corrupt rows
            logger.warning("Skipping corrupt passkey credential_id pk=%s", cred.pk)
    return out


def begin_registration(request: HttpRequest, user: Any) -> dict[str, Any]:
    """Store registration challenge; return PublicKeyCredentialCreationOptions JSON dict."""
    options = generate_registration_options(
        rp_id=passkey_rp_id(),
        rp_name=passkey_rp_name(),
        user_id=_user_handle(user),
        user_name=_webauthn_user_name(user),
        user_display_name=_webauthn_display_name(user),
        exclude_credentials=_exclude_credentials(user),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    now = int(time.time())
    request.session[_SESSION_REG_CHALLENGE] = bytes_to_base64url(options.challenge)
    request.session[_SESSION_REG_USER] = user.pk
    request.session[_SESSION_REG_EXPIRES] = now + challenge_ttl_seconds()
    request.session.modified = True
    return json.loads(options_to_json(options))


def complete_registration(
    request: HttpRequest,
    *,
    credential: dict[str, Any],
    device_name: str = "",
) -> PasskeyCredential:
    """Verify attestation and persist a new PasskeyCredential for the session user."""
    from webauthn.helpers import base64url_to_bytes

    challenge_b64 = request.session.get(_SESSION_REG_CHALLENGE)
    user_id = request.session.get(_SESSION_REG_USER)
    expires = int(request.session.get(_SESSION_REG_EXPIRES) or 0)
    if not challenge_b64 or not user_id or int(time.time()) > expires:
        clear_registration_challenge(request)
        raise ValueError("Срок действия запроса истек. Начните регистрацию снова.")

    if request.user.pk != user_id:
        clear_registration_challenge(request)
        raise ValueError("Сессия регистрации не совпадает с текущим пользователем.")

    verified = verify_registration_response(
        credential=credential,
        expected_challenge=base64url_to_bytes(challenge_b64),
        expected_rp_id=passkey_rp_id(),
        expected_origin=passkey_origin(),
        require_user_verification=True,
    )
    cred_id = bytes_to_base64url(verified.credential_id)
    if PasskeyCredential.objects.filter(credential_id=cred_id).exists():
        clear_registration_challenge(request)
        raise ValueError("Этот ключ уже зарегистрирован.")

    name = (device_name or "").strip()[:120]
    if not name:
        name = "Ключ"
    row = PasskeyCredential.objects.create(
        user_id=request.user.pk,
        credential_id=cred_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        device_name=name,
    )
    clear_registration_challenge(request)
    return row


def clear_registration_challenge(request: HttpRequest) -> None:
    """Drop registration challenge keys from the session."""
    for key in (_SESSION_REG_CHALLENGE, _SESSION_REG_USER, _SESSION_REG_EXPIRES):
        request.session.pop(key, None)
    request.session.modified = True


def begin_authentication(request: HttpRequest, *, next_url: str = "") -> dict[str, Any]:
    """Store auth challenge; return discoverable PublicKeyCredentialRequestOptions."""
    options = generate_authentication_options(
        rp_id=passkey_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    now = int(time.time())
    request.session[_SESSION_AUTH_CHALLENGE] = bytes_to_base64url(options.challenge)
    request.session[_SESSION_AUTH_EXPIRES] = now + challenge_ttl_seconds()
    request.session[_SESSION_AUTH_NEXT] = (next_url or "").strip()
    request.session.modified = True
    return json.loads(options_to_json(options))


def complete_authentication(
    request: HttpRequest,
    *,
    credential: dict[str, Any],
) -> tuple[Any, str]:
    """Verify assertion; return (staff user, next_url)."""
    from webauthn.helpers import base64url_to_bytes

    challenge_b64 = request.session.get(_SESSION_AUTH_CHALLENGE)
    expires = int(request.session.get(_SESSION_AUTH_EXPIRES) or 0)
    next_url = str(request.session.get(_SESSION_AUTH_NEXT) or "").strip() or "/admin/"
    if not challenge_b64 or int(time.time()) > expires:
        clear_authentication_challenge(request)
        raise ValueError("Срок действия запроса истек. Попробуйте снова.")

    raw_id = credential.get("id") or credential.get("rawId")
    if not isinstance(raw_id, str) or not raw_id:
        clear_authentication_challenge(request)
        raise ValueError("Некорректный ответ ключа доступа.")

    # Browser credential.id is already base64url; rawId may be the same after toJSON().
    cred_id = raw_id
    try:
        row = PasskeyCredential.objects.select_related("user").get(credential_id=cred_id)
    except PasskeyCredential.DoesNotExist:
        # Some browsers send only rawId; normalize if needed.
        try:
            as_bytes = base64url_to_bytes(cred_id)
            cred_id = bytes_to_base64url(as_bytes)
            row = PasskeyCredential.objects.select_related("user").get(credential_id=cred_id)
        except Exception as exc:
            clear_authentication_challenge(request)
            raise ValueError("Ключ доступа не найден.") from exc

    user = row.user
    if not user.is_active or not user.is_staff:
        clear_authentication_challenge(request)
        raise ValueError("Учётная запись не имеет доступа в админку.")

    verified = verify_authentication_response(
        credential=credential,
        expected_challenge=base64url_to_bytes(challenge_b64),
        expected_rp_id=passkey_rp_id(),
        expected_origin=passkey_origin(),
        credential_public_key=bytes(row.public_key),
        credential_current_sign_count=row.sign_count,
        require_user_verification=True,
    )
    row.sign_count = verified.new_sign_count
    row.last_used_at = timezone.now()
    row.save(update_fields=["sign_count", "last_used_at"])
    clear_authentication_challenge(request)
    return user, next_url


def clear_authentication_challenge(request: HttpRequest) -> None:
    """Drop authentication challenge keys from the session."""
    for key in (_SESSION_AUTH_CHALLENGE, _SESSION_AUTH_EXPIRES, _SESSION_AUTH_NEXT):
        request.session.pop(key, None)
    request.session.modified = True


def passkeys_for_user(user: Any) -> list[PasskeyCredential]:
    """List passkeys for a user (newest first)."""
    return list(PasskeyCredential.objects.filter(user_id=user.pk))
