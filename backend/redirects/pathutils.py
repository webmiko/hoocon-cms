"""Path helpers for Redirect: normalize and reject open redirects."""

from __future__ import annotations

from django.core.exceptions import ValidationError

# Breaks or injects the generated nginx map (``from to;``) or the Location header.
_UNSAFE_PATH_CHARS = frozenset(" \t;{}\"'\\$")


def validate_internal_path(value: str) -> None:
    """Reject open redirects and paths unsafe for the nginx map.

    Args:
        value: Candidate path (e.g. ``/catalog``).

    Raises:
        ValidationError: If the value is empty, relative, protocol-relative,
            contains a URL scheme, whitespace, control characters or nginx
            syntax (``; { } " ' \\ $``).
    """
    if not value or not value.startswith("/") or value.startswith("//"):
        raise ValidationError("Путь должен начинаться с одного «/», например /catalog.")
    if "://" in value:
        raise ValidationError("Внешние адреса запрещены — только путь на этом сайте.")
    if any(ch in _UNSAFE_PATH_CHARS or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValidationError("В пути нельзя использовать пробелы, управляющие символы и ; { } \" ' \\ $.")


def is_safe_internal_path(value: str) -> bool:
    """True when :func:`validate_internal_path` accepts ``value``."""
    try:
        validate_internal_path(value)
    except ValidationError:
        return False
    return True


def normalize_path(path: str) -> str:
    """Normalize a request or stored path for lookup (no trailing slash).

    Args:
        path: Raw path, optionally without a leading slash.

    Returns:
        Path starting with ``/`` and without a trailing slash (except ``/``).
    """
    cleaned = path.strip() or "/"
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned
