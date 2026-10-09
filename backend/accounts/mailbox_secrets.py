"""At-rest encryption for StaffMailbox IMAP/SMTP app passwords.

New saves use Fernet (AES-128-CBC + HMAC) with ``MAILBOX_ENCRYPTION_KEY`` or
a key derived from ``SECRET_KEY`` — a DB dump alone does not reveal the
password. Legacy ``signed1:`` rows (base64 + HMAC, readable without any key)
and plaintext rows still decode and are re-encrypted on the next save.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.signing import BadSignature, loads

_PREFIX = "fernet1:"
_LEGACY_SIGNED_PREFIX = "signed1:"
_LEGACY_SALT = "hoocon.staff-mailbox.imap"
_HKDF_INFO = b"hoocon.staff-mailbox.fernet"


def _fernet() -> Fernet:
    explicit = (getattr(settings, "MAILBOX_ENCRYPTION_KEY", "") or "").strip()
    if explicit:
        return Fernet(explicit.encode())
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(
        settings.SECRET_KEY.encode(),
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def _decode_legacy(value: str) -> str:
    if not value.startswith(_LEGACY_SIGNED_PREFIX):
        return value
    try:
        decoded = loads(value[len(_LEGACY_SIGNED_PREFIX) :], salt=_LEGACY_SALT)
    except BadSignature:
        return ""
    return decoded if isinstance(decoded, str) else str(decoded)


def encrypt_mailbox_secret(plain: str) -> str:
    """Return a Fernet token; empty or already-encrypted input is unchanged.

    Args:
        plain: app password, legacy ``signed1:`` value or a Fernet token.

    Returns:
        ``fernet1:``-prefixed token or empty string.
    """
    value = (plain or "").strip()
    if not value or value.startswith(_PREFIX):
        return value
    decoded = _decode_legacy(value)
    if not decoded:
        if value.startswith(_LEGACY_SIGNED_PREFIX):
            # Signature no longer verifies (rotated SECRET_KEY, corruption).
            # Keep the stored token intact — do not silently wipe the password.
            return value
        return ""
    return _PREFIX + _fernet().encrypt(decoded.encode()).decode()


def decrypt_mailbox_secret(stored: str) -> str:
    """Decrypt a stored value; legacy signed and plaintext rows decode too.

    Args:
        stored: value from ``StaffMailbox.imap_password``.

    Returns:
        Plain app password, or empty string if the token is invalid.
    """
    value = stored or ""
    if not value.startswith(_PREFIX):
        return _decode_legacy(value)
    try:
        return _fernet().decrypt(value[len(_PREFIX) :].encode()).decode()
    except InvalidToken:
        return ""
