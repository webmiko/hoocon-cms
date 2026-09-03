"""Named staff Groups and permission matrices for Django Admin.

Groups (Russian names as shown in Admin → Groups):

* **Админ** — full write on project apps (catalog, content, leads, CRM,
  redirects, site settings, social). Not a Django superuser: no auth
  user/group management. Sees all leads/CRM (no manager scope).
* **Менеджер** — RFQ + CRM workflow (add/change, no delete); catalog
  view-only for SKU context; ``view_user`` for assignee FK. Scoped to
  own leads/clients (+ shared NEW pool). Support chat (``supportchat``):
  view/add/change, no delete — when that app ships.
* **Аналитик** — same surface as manager but **view-only**; sees all
  leads/CRM/stats across managers (unscoped). Support chat: view-only
  when the app ships.

Sync with ``manage.py sync_staff_groups`` (idempotent). Users still need
``is_staff=True`` to open Admin; scoping is ``scope_*_for_manager`` +
:func:`staff_sees_all_leads`.
"""

from __future__ import annotations

from typing import Any, Final

# Group names (exact strings stored in auth_group.name).
GROUP_ADMIN: Final = "Админ"
GROUP_MANAGER: Final = "Менеджер"
GROUP_ANALYST: Final = "Аналитик"

STAFF_GROUP_NAMES: Final[tuple[str, ...]] = (
    GROUP_ADMIN,
    GROUP_MANAGER,
    GROUP_ANALYST,
)

# Groups that bypass manager lead/CRM scope (see all rows + full stats).
_UNSCOPED_GROUP_NAMES: Final[frozenset[str]] = frozenset(
    {GROUP_ADMIN, GROUP_ANALYST},
)

# (app_label, model meta.model_name) — Django default CRUD uses model_name.
_CATALOG_MODELS: Final[tuple[str, ...]] = (
    "category",
    "product",
    "sku",
    "attribute",
    "attributevalue",
    "productfile",
    "productimage",
)
_CONTENT_MODELS: Final[tuple[str, ...]] = ("page", "article", "news")
_CRM_MODELS: Final[tuple[str, ...]] = ("client", "activity", "emailmessage")


def _perms(
    app_label: str,
    model: str,
    *,
    actions: tuple[str, ...] = ("view", "add", "change", "delete"),
) -> frozenset[tuple[str, str]]:
    """Build ``(app_label, codename)`` pairs for a model."""
    return frozenset((app_label, f"{action}_{model}") for action in actions)


def _view_only(app_label: str, models: tuple[str, ...]) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for model in models:
        out |= _perms(app_label, model, actions=("view",))
    return frozenset(out)


def _crud(app_label: str, models: tuple[str, ...]) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for model in models:
        out |= _perms(app_label, model)
    return frozenset(out)


def _write_no_delete(
    app_label: str,
    models: tuple[str, ...],
) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for model in models:
        out |= _perms(app_label, model, actions=("view", "add", "change"))
    return frozenset(out)


_VIEW_USER: Final[frozenset[tuple[str, str]]] = frozenset(
    {("auth", "view_user")},
)

_SUPPORTCHAT_MODELS: Final[tuple[str, ...]] = (
    "conversation",
    "message",
    "supportschedule",
    "supportscheduleday",
    "supportscheduleinterval",
)

_WEBPUSH_MODELS: Final[tuple[str, ...]] = ("pushsubscription",)

_ANALYTICS_MODELS: Final[tuple[str, ...]] = ("pagedailystat", "sitedailystat")

_ADMIN_PERMS: Final[frozenset[tuple[str, str]]] = (
    _crud("catalog", _CATALOG_MODELS)
    | _crud("content", _CONTENT_MODELS)
    | _crud("leads", ("lead",))
    | _crud("crm", _CRM_MODELS)
    | _crud("redirects", ("redirect",))
    | _crud("sitesettings", ("sitesettings",))
    | _crud("social", ("socialpost",))
    | _crud("supportchat", _SUPPORTCHAT_MODELS)
    | _crud("webpush", _WEBPUSH_MODELS)
    | _view_only("analytics", _ANALYTICS_MODELS)
    | _VIEW_USER
)

# Manager: leads + CRM write (no delete), catalog view, supportchat write (no delete).
_MANAGER_PERMS: Final[frozenset[tuple[str, str]]] = (
    _write_no_delete("leads", ("lead",))
    | _write_no_delete("crm", _CRM_MODELS)
    | _write_no_delete("supportchat", _SUPPORTCHAT_MODELS)
    | _write_no_delete("webpush", _WEBPUSH_MODELS)
    | _view_only("catalog", _CATALOG_MODELS)
    | _view_only("analytics", _ANALYTICS_MODELS)
    | _VIEW_USER
)

# Analyst: same surface as manager, view-only (+ view_user for assignee labels).
_ANALYST_PERMS: Final[frozenset[tuple[str, str]]] = (
    _view_only("leads", ("lead",))
    | _view_only("crm", _CRM_MODELS)
    | _view_only("catalog", _CATALOG_MODELS)
    | _view_only("supportchat", _SUPPORTCHAT_MODELS)
    | _view_only("webpush", _WEBPUSH_MODELS)
    | _view_only("analytics", _ANALYTICS_MODELS)
    | _VIEW_USER
)

STAFF_GROUP_PERMISSIONS: Final[dict[str, frozenset[tuple[str, str]]]] = {
    GROUP_ADMIN: _ADMIN_PERMS,
    GROUP_MANAGER: _MANAGER_PERMS,
    GROUP_ANALYST: _ANALYST_PERMS,
}


def staff_sees_all_leads(user: Any) -> bool:
    """Whether Admin lead/CRM querysets skip manager scoping.

    Superuser, group «Админ», and group «Аналитик» see every lead/client
    (analysts are view-only via permissions; admins have full write).

    Args:
        user: Django user (may be anonymous).

    Returns:
        True when scope helpers must return the unfiltered queryset.
    """
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return False
    groups = getattr(user, "groups", None)
    if groups is None:
        return False
    return groups.filter(name__in=_UNSCOPED_GROUP_NAMES).exists()
