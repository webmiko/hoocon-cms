"""Constant-time comparison for secrets presented by outside callers."""

from __future__ import annotations

import hmac


def secrets_equal(expected: str, presented: str) -> bool:
    """``hmac.compare_digest`` on UTF-8 bytes.

    On ``str`` it raises ``TypeError`` for non-ASCII input, turning a forged
    webhook token into a 500 instead of a 403.
    """
    return hmac.compare_digest(expected.encode("utf-8"), presented.encode("utf-8"))
