"""Idempotent sync of staff Groups and their permissions."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import Group, Permission
from django.db import transaction

from accounts.roles import STAFF_GROUP_NAMES, STAFF_GROUP_PERMISSIONS

logger = logging.getLogger(__name__)


def ensure_staff_groups(*, dry_run: bool = False) -> dict[str, Any]:
    """Create/update Админ, Менеджер, Аналитик and set exact permissions.

    Missing permissions in the DB are skipped with a warning (e.g. before
    migrations). Extra permissions on a group are removed so the matrix
    stays the source of truth.

    Args:
        dry_run: When True, compute the plan without writing.

    Returns:
        Summary ``{"groups": {name: {"added": n, "removed": n, "kept": n}}}``.
    """
    summary: dict[str, Any] = {"groups": {}, "dry_run": dry_run}

    with transaction.atomic():
        for name in STAFF_GROUP_NAMES:
            wanted = STAFF_GROUP_PERMISSIONS[name]
            group_summary = _sync_one_group(name, wanted, dry_run=dry_run)
            summary["groups"][name] = group_summary
        if dry_run:
            transaction.set_rollback(True)

    return summary


def _sync_one_group(
    name: str,
    wanted: frozenset[tuple[str, str]],
    *,
    dry_run: bool,
) -> dict[str, int]:
    """Sync a single Group to ``wanted`` permission pairs."""
    group, _created = Group.objects.get_or_create(name=name)
    current = {(p.content_type.app_label, p.codename) for p in group.permissions.select_related("content_type")}
    target_perms = _resolve_permissions(wanted)
    target_keys = {(p.content_type.app_label, p.codename) for p in target_perms}

    to_add = target_keys - current
    to_remove = current - target_keys
    kept = len(current & target_keys)

    if not dry_run:
        if to_add or to_remove:
            group.permissions.set(target_perms)
        logger.info(
            "staff_group_synced name=%s added=%s removed=%s kept=%s",
            name,
            len(to_add),
            len(to_remove),
            kept,
        )

    return {
        "added": len(to_add),
        "removed": len(to_remove),
        "kept": kept,
        "total": len(target_keys),
    }


def _resolve_permissions(
    wanted: frozenset[tuple[str, str]],
) -> list[Permission]:
    """Load Permission rows; warn and skip unknown (app_label, codename)."""
    found: list[Permission] = []
    for app_label, codename in sorted(wanted):
        try:
            perm = Permission.objects.select_related("content_type").get(
                content_type__app_label=app_label,
                codename=codename,
            )
        except Permission.DoesNotExist:
            logger.warning(
                "staff_group_perm_missing app=%s codename=%s",
                app_label,
                codename,
            )
            continue
        found.append(perm)
    return found
