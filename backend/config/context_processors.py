"""Template context processors for Hoocon CMS."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def static_version(_request: HttpRequest) -> dict[str, str]:
    """Cache-bust token for admin static assets (?v=).

    In DEBUG without BUILD_SHA uses max mtime of theme CSS + JS.

    Args:
        _request: unused request (Django context processor signature).

    Returns:
        Dict with STATIC_VERSION key.
    """
    version = getattr(settings, "BUILD_SHA", "").strip()
    if not version and settings.DEBUG:
        base = settings.BASE_DIR / "static/admin"
        mtimes: list[int] = []
        for rel in (
            "css/hoocon-unfold-extras.css",
            "js/hoocon-admin-leads-sticker.js",
        ):
            path = base / rel
            if path.is_file():
                mtimes.append(int(path.stat().st_mtime))
        if mtimes:
            version = str(max(mtimes))
    return {"STATIC_VERSION": version or "dev"}


def release_info(_request: HttpRequest) -> dict[str, str]:
    """Expose release label to Admin templates (dashboard, base).

    Args:
        _request: unused request (Django context processor signature).

    Returns:
        Dict with RELEASE_LABEL (e.g. ``v0.0.2 beta``).
    """
    from config.release import release_label

    return {"RELEASE_LABEL": release_label()}


def new_leads_sticker(request: HttpRequest) -> dict[str, object]:
    """Admin sticker: count of leads with status=new + inbox URL.

    Args:
        request: current HTTP request (needs authenticated staff).

    Returns:
        HOOCON_NEW_LEADS_COUNT (int), HOOCON_NEW_LEADS_URL (str),
        HOOCON_NEW_LEADS_COUNT_URL (str for JSON poll). Empty for anon.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {
            "HOOCON_NEW_LEADS_COUNT": 0,
            "HOOCON_NEW_LEADS_URL": "",
            "HOOCON_NEW_LEADS_COUNT_URL": "",
        }

    if not user.has_perm("leads.view_lead"):
        return {
            "HOOCON_NEW_LEADS_COUNT": 0,
            "HOOCON_NEW_LEADS_URL": "",
            "HOOCON_NEW_LEADS_COUNT_URL": "",
        }

    from django.urls import reverse

    from leads.services import count_new_leads, new_leads_changelist_url

    return {
        "HOOCON_NEW_LEADS_COUNT": count_new_leads(user=user),
        "HOOCON_NEW_LEADS_URL": new_leads_changelist_url(),
        "HOOCON_NEW_LEADS_COUNT_URL": reverse("admin:leads_lead_new_count"),
    }
