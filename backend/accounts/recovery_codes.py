"""Generate and consume hashed superuser Admin recovery codes.

Format ``XXXX-XXXX`` (crockford-ish alphabet without ambiguous chars).
Pepper tag differs from email OTP so hashes never collide across channels.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import SuperuserRecoveryCode

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

logger = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1
_SEGMENT_LEN = 4
_CODE_RE = re.compile(
    r"^[" + _ALPHABET + r"]{4}-[" + _ALPHABET + r"]{4}$",
)


def hash_recovery_code(code: str) -> str:
    """Hash normalized recovery code with SECRET_KEY pepper."""
    pepper = str(settings.SECRET_KEY).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(pepper)
    digest.update(b"|admin-recovery-otp|")
    digest.update(normalize_recovery_code(code).encode("utf-8"))
    return digest.hexdigest()


def normalize_recovery_code(raw: str) -> str:
    """Uppercase and strip separators; re-insert dash for the canonical form."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", (raw or "").strip()).upper()
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:]}"
    return cleaned


def generate_recovery_code() -> str:
    """One cryptographically strong ``XXXX-XXXX`` code."""
    first = "".join(secrets.choice(_ALPHABET) for _ in range(_SEGMENT_LEN))
    second = "".join(secrets.choice(_ALPHABET) for _ in range(_SEGMENT_LEN))
    return f"{first}-{second}"


def unused_recovery_code_count(user: AbstractBaseUser) -> int:
    """Count unused recovery codes for user."""
    if not getattr(user, "pk", None):
        return 0
    return SuperuserRecoveryCode.objects.filter(user_id=user.pk, used_at__isnull=True).count()


@transaction.atomic
def replace_recovery_codes(
    user: AbstractBaseUser,
    *,
    count: int = RECOVERY_CODE_COUNT,
) -> list[str]:
    """Delete all codes for user, create ``count`` new ones; return plaintext once.

    Caller must ensure ``user.is_superuser``. Old codes (used and unused) are removed.
    """
    if not getattr(user, "is_superuser", False):
        raise ValueError("Recovery codes are only for superusers.")
    SuperuserRecoveryCode.objects.filter(user_id=user.pk).delete()
    plain: list[str] = []
    rows: list[SuperuserRecoveryCode] = []
    for _ in range(max(1, count)):
        code = generate_recovery_code()
        # Extremely unlikely collision within the batch; regenerate if needed.
        while code in plain:
            code = generate_recovery_code()
        plain.append(code)
        rows.append(
            SuperuserRecoveryCode(
                user_id=user.pk,
                code_hash=hash_recovery_code(code),
            ),
        )
    SuperuserRecoveryCode.objects.bulk_create(rows)
    logger.info(
        "Replaced recovery codes for superuser pk=%s count=%s",
        user.pk,
        len(plain),
    )
    return plain


def consume_recovery_code(user: AbstractBaseUser, raw_code: str) -> bool:
    """Mark matching unused code as used. Returns True on success.

    Only active staff superusers may consume. Constant-time-ish: always hash,
    then scan unused hashes for this user with ``compare_digest``.
    """
    if not (
        getattr(user, "is_active", False) and getattr(user, "is_staff", False) and getattr(user, "is_superuser", False)
    ):
        return False

    normalized = normalize_recovery_code(raw_code)
    if not _CODE_RE.match(normalized):
        return False

    actual = hash_recovery_code(normalized)
    candidates = list(
        SuperuserRecoveryCode.objects.filter(user_id=user.pk, used_at__isnull=True).only(
            "pk",
            "code_hash",
        ),
    )
    matched: SuperuserRecoveryCode | None = None
    for row in candidates:
        if hmac.compare_digest(row.code_hash, actual):
            matched = row
            # Keep scanning to reduce early-exit timing differences across rows.
    if matched is None:
        return False

    updated = SuperuserRecoveryCode.objects.filter(pk=matched.pk, used_at__isnull=True).update(
        used_at=timezone.now(),
    )
    if updated != 1:
        return False
    logger.info("Consumed recovery code for superuser pk=%s", user.pk)
    return True
