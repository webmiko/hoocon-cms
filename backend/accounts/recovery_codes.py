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
from enum import Enum
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
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


class RecoveryAttempt(Enum):
    """Outcome of :func:`attempt_recovery_code`."""

    OK = "ok"
    INVALID = "invalid"
    LOCKED = "locked"


def recovery_fail_limit() -> int:
    """Wrong recovery codes allowed per login before the lock."""
    return int(getattr(settings, "ADMIN_RECOVERY_MAX_FAILS", 5))


def recovery_lock_seconds() -> int:
    """How long the per-login recovery lock lasts."""
    return int(getattr(settings, "ADMIN_RECOVERY_LOCK_SECONDS", 900))


def looks_like_recovery_code(raw_code: str) -> bool:
    """True for ``XXXX-XXXX`` input (never a 6-digit email OTP)."""
    return bool(_CODE_RE.match(normalize_recovery_code(raw_code)))


def _fail_key(subject: str) -> str:
    digest = hashlib.sha256(subject.strip().lower().encode("utf-8")).hexdigest()
    return f"admin-recovery-fails:{digest}"


def _register_failure(subject: str) -> None:
    key = _fail_key(subject)
    cache.add(key, 0, timeout=recovery_lock_seconds())
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=recovery_lock_seconds())


def recovery_subject(user: AbstractBaseUser | None, login: str = "") -> str:
    """Limiter key: the user row when known, otherwise the typed login."""
    if user is not None and getattr(user, "pk", None):
        return f"user:{user.pk}"
    return f"login:{login}"


def attempt_recovery_code(
    user: AbstractBaseUser | None,
    raw_code: str,
    *,
    subject: str,
) -> RecoveryAttempt:
    """Consume a recovery code behind a per-login failure limit.

    The lock is checked **before** hashing so a locked login gets no oracle,
    and every miss (unknown user included) counts against ``subject``.
    """
    key = _fail_key(subject)
    if int(cache.get(key) or 0) >= recovery_fail_limit():
        return RecoveryAttempt.LOCKED
    if user is not None and consume_recovery_code(user, raw_code):
        cache.delete(key)
        return RecoveryAttempt.OK
    _register_failure(subject)
    return RecoveryAttempt.INVALID
