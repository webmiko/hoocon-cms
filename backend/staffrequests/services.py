"""Who may file, read, and switch the manager-request widget."""

from __future__ import annotations

from typing import Any

from accounts.roles import GROUP_ADMIN, GROUP_MANAGER
from staffrequests.models import StaffRequestSettings


def requests_enabled() -> bool:
    """True when the admin has switched the widget on."""
    return StaffRequestSettings.load().enabled


def can_manage_queue(user: Any) -> bool:
    """Admin and superuser see every request and set the status."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    groups = getattr(user, "groups", None)
    if groups is None:
        return False
    return groups.filter(name=GROUP_ADMIN).exists()


def can_file(user: Any) -> bool:
    """Managers file their own requests. Admins can file too."""
    if can_manage_queue(user):
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    groups = getattr(user, "groups", None)
    if groups is None:
        return False
    return groups.filter(name=GROUP_MANAGER).exists()


def can_toggle(user: Any) -> bool:
    """The same people who run the queue may switch the widget."""
    return can_manage_queue(user)
