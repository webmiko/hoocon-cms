"""Callbacks for django-unfold (sidebar badges, permissions, static URLs)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.templatetags.static import static


def badge_new_leads(request: HttpRequest) -> int | str:
    """Return count of unread new leads for the sidebar badge.

    Args:
        request: current admin request.

    Returns:
        Positive int when there are new leads the user may view;
        empty string hides the badge.
    """
    if not _can_view_leads(request):
        return ""
    from leads.services import count_new_leads

    count = count_new_leads(user=request.user)
    return count if count > 0 else ""


def badge_support_unread(request: HttpRequest) -> int | str:
    """Unread support conversations for the Unfold sidebar badge."""
    if not _can_view_conversations(request):
        return ""
    from supportchat.services import count_staff_unread

    count = count_staff_unread()
    return count if count > 0 else ""


def perm_view_conversation(request: HttpRequest) -> bool:
    """Whether the user may see support conversations in the sidebar."""
    return _can_view_conversations(request)


def perm_view_webpush(request: HttpRequest) -> bool:
    """Whether the user may see Web Push subscriptions in the sidebar."""
    user = getattr(request, "user", None)
    return bool(
        user and user.is_authenticated and user.has_perm("webpush.view_pushsubscription"),
    )


def dashboard_callback(request: HttpRequest, context: dict[str, Any]) -> dict[str, Any]:
    """Inject Hoocon dashboard data into Unfold Admin index.

    Args:
        request: admin index request.
        context: Unfold/Django Admin template context.

    Returns:
        Context with ``hoocon_dashboard`` when staff is authenticated.
    """
    from config.dashboard import build_admin_dashboard

    context.update(build_admin_dashboard(request))
    return context


def perm_view_lead(request: HttpRequest) -> bool:
    """Whether the user may see leads in the Unfold sidebar."""
    return _can_view_leads(request)


def perm_view_client(request: HttpRequest) -> bool:
    """Whether the user may see CRM clients in the Unfold sidebar."""
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.has_perm("crm.view_client"))


def perm_view_sku(request: HttpRequest) -> bool:
    """Whether the user may see catalog SKUs in the Unfold sidebar."""
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.has_perm("catalog.view_sku"))


def perm_view_sitesettings(request: HttpRequest) -> bool:
    """Whether the user may see site settings in the Unfold sidebar."""
    user = getattr(request, "user", None)
    return bool(
        user and user.is_authenticated and user.has_perm("sitesettings.view_sitesettings"),
    )


def unfold_extras_css(request: HttpRequest) -> str:
    """URL of thin CSS for Unfold shell (cache-busted)."""
    del request
    url = static("admin/css/hoocon-unfold-extras.css")
    from django.conf import settings

    version = getattr(settings, "BUILD_SHA", "").strip()
    if not version and settings.DEBUG:
        path = settings.BASE_DIR / "static/admin/css/hoocon-unfold-extras.css"
        if path.is_file():
            version = str(int(path.stat().st_mtime))
    if version:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}v={version}"
    return url


def _can_view_leads(request: HttpRequest) -> bool:
    """Staff with leads.view_lead (superuser included via has_perm)."""
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.has_perm("leads.view_lead"))


def _can_view_conversations(request: HttpRequest) -> bool:
    """Staff with supportchat.view_conversation."""
    user = getattr(request, "user", None)
    return bool(
        user and user.is_authenticated and user.has_perm("supportchat.view_conversation"),
    )
