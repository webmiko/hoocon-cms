"""Named staff Groups and permission matrices for Django Admin.

Groups (Russian names as shown in Admin → Groups):

* **Админ** — full write on project apps (catalog, content, leads, CRM,
  redirects, site settings, social). Not a Django superuser: no auth
  user/group management.
* **Менеджер** — RFQ + CRM workflow (add/change, no delete); catalog/content
  read for SKU context; ``view_user`` for assignee FK.
* **Аналитик** — read-only catalog / content / leads / CRM / redirects.

Sync with ``manage.py sync_staff_groups`` (idempotent). Users still need
``is_staff=True`` to open Admin; scoping for managers is separate
(``scope_*_for_manager``).
"""

from __future__ import annotations

from typing import Final

# Group names (exact strings stored in auth_group.name).
GROUP_ADMIN: Final = "Админ"
GROUP_MANAGER: Final = "Менеджер"
GROUP_ANALYST: Final = "Аналитик"

STAFF_GROUP_NAMES: Final[tuple[str, ...]] = (
    GROUP_ADMIN,
    GROUP_MANAGER,
    GROUP_ANALYST,
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

_ADMIN_PERMS: Final[frozenset[tuple[str, str]]] = (
    _crud("catalog", _CATALOG_MODELS)
    | _crud("content", _CONTENT_MODELS)
    | _crud("leads", ("lead",))
    | _crud("crm", _CRM_MODELS)
    | _crud("redirects", ("redirect",))
    | _crud("sitesettings", ("sitesettings",))
    | _crud("social", ("socialpost",))
    | _VIEW_USER
)

_MANAGER_PERMS: Final[frozenset[tuple[str, str]]] = (
    _write_no_delete("leads", ("lead",))
    | _write_no_delete("crm", _CRM_MODELS)
    | _view_only("catalog", _CATALOG_MODELS)
    | _view_only("content", _CONTENT_MODELS)
    | _view_only("social", ("socialpost",))
    | _VIEW_USER
)

_ANALYST_PERMS: Final[frozenset[tuple[str, str]]] = (
    _view_only("catalog", _CATALOG_MODELS)
    | _view_only("content", _CONTENT_MODELS)
    | _view_only("leads", ("lead",))
    | _view_only("crm", _CRM_MODELS)
    | _view_only("redirects", ("redirect",))
    | _view_only("social", ("socialpost",))
)

STAFF_GROUP_PERMISSIONS: Final[dict[str, frozenset[tuple[str, str]]]] = {
    GROUP_ADMIN: _ADMIN_PERMS,
    GROUP_MANAGER: _MANAGER_PERMS,
    GROUP_ANALYST: _ANALYST_PERMS,
}
