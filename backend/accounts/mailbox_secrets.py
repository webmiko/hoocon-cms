"""At-rest encoding for StaffMailbox IMAP/SMTP app passwords.

Plaintext rows (legacy) still decrypt as themselves. New saves are signed with
Django's SECRET_KEY so a DB dump is not enough to reuse the mailbox.
"""

from __future__ import annotations

from django.core.signing import BadSignature, dumps, loads

_PREFIX = "signed1:"
_SALT = "hoocon.staff-mailbox.imap"


def encrypt_mailbox_secret(plain: str) -> str:
    """Return a signed token, or empty / already-signed input unchanged.

    Args:
        plain: app password or previously signed value.

    Returns:
        Signed string, empty string, or the original signed value.
    """
    value = (plain or "").strip()
    if not value or value.startswith(_PREFIX):
        return value
    return f"{_PREFIX}{dumps(value, salt=_SALT, compress=True)}"


def decrypt_mailbox_secret(stored: str) -> str:
    """Decode a signed token; leftover plaintext is returned as-is.

    Args:
        stored: value from ``StaffMailbox.imap_password``.

    Returns:
        Plain app password, or empty string if the signature is invalid.
    """
    value = stored or ""
    if not value.startswith(_PREFIX):
        return value
    try:
        decoded = loads(value[len(_PREFIX) :], salt=_SALT)
    except BadSignature:
        return ""
    return decoded if isinstance(decoded, str) else str(decoded)
