"""Parse an id from a query string without Unicode digit tricks.

``str.isdigit`` is true for ``²``, and ``int("²")`` then raises ValueError.
"""

from __future__ import annotations


def query_int(value: object) -> int | None:
    """ASCII digits only. Anything else, including ``²`` and NUL, is None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or not text.isascii() or not text.isdigit():
        return None
    return int(text)
