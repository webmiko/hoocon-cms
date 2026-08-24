"""Versioned static URLs for Admin assets (cache-bust on deploy)."""

from __future__ import annotations

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage


def versioned_static(relative_path: str) -> str:
    """Return a static URL with ``?v=`` when BUILD_SHA or dev mtime is known.

    Admin PNG/icons use stable filenames; nginx serves /static/ with long
    immutable cache — without a query token browsers keep old icons after deploy.

    Args:
        relative_path: path under STATICFILES_DIRS, e.g. ``admin/img/foo.png``.

    Returns:
        Static URL, optionally suffixed with ``?v=<token>``.
    """
    url = staticfiles_storage.url(relative_path)
    version = getattr(settings, "BUILD_SHA", "").strip()
    if not version and settings.DEBUG:
        path = settings.BASE_DIR / "static" / relative_path
        if path.is_file():
            version = str(int(path.stat().st_mtime))
    if version:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}v={version}"
    return url
