"""Registry-wide invariants: new code is checked without writing a new test.

Global review 2026-10-09: admin actions without permissions (H7), cabinet data
before email verification (C1), settings for a package that is not installed
(H2) and rules pointing at missing scripts (M38) all passed a green suite,
because each test covered one object instead of the whole registry.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import warnings
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import AdminSite, all_sites
from django.urls import URLPattern, URLResolver, path
from django.utils.module_loading import import_string
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from accounts.roles import STAFF_GROUP_PERMISSIONS
from cabinet import urls as cabinet_urls
from cabinet.auth import IsClientAccount

ROOT = Path(__file__).resolve().parents[2]


# ── Admin actions ────────────────────────────────────────────────────────────


def staff_reachable_models() -> set[tuple[str, str]]:
    """``(app_label, model_name)`` any staff role can open in Admin."""
    reachable: set[tuple[str, str]] = set()
    for perms in STAFF_GROUP_PERMISSIONS.values():
        for app_label, codename in perms:
            _action, _, model_name = codename.partition("_")
            reachable.add((app_label, model_name))
    return reachable


def unguarded_actions(sites: Iterable[AdminSite]) -> list[tuple[str, str, str]]:
    """Admin actions without ``allowed_permissions`` as ``(app_label, model, action)``."""
    found: list[tuple[str, str, str]] = []
    for site in sites:
        for model, registered in site._registry.items():
            model_admin: Any = registered
            for action in model_admin._get_base_actions():
                if not getattr(action.func, "allowed_permissions", None):
                    found.append((model._meta.app_label, str(model._meta.model_name), action.name))
    return found


def test_admin_actions_are_permission_gated_or_out_of_staff_reach() -> None:
    """H7: an action without allowed_permissions runs for anyone who can open the list."""
    reachable = staff_reachable_models()
    exposed = [action for action in unguarded_actions(all_sites) if (action[0], action[1]) in reachable]
    assert exposed == []


def test_unguarded_action_detector_flags_a_plain_action() -> None:
    from django.contrib.auth.models import Group

    def promote(modeladmin: Any, request: Any, queryset: Any) -> None:
        return None

    class GroupAdmin(admin.ModelAdmin):
        actions = [promote]

    site = AdminSite(name="invariant-probe")
    site.register(Group, GroupAdmin)
    assert ("auth", "group", "promote") in unguarded_actions([site])


# ── Client cabinet ───────────────────────────────────────────────────────────


def walk_routes(patterns: Iterable[URLPattern | URLResolver], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Yield ``(route, callback)`` for every leaf URL pattern."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from walk_routes(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), pattern.callback


def routes_without_verified_client(patterns: Iterable[URLPattern | URLResolver]) -> list[str]:
    """Routes whose view does not require :class:`IsClientAccount`."""
    missing = []
    for route, callback in walk_routes(patterns):
        view_cls = getattr(callback, "cls", None)
        perms = getattr(view_cls, "permission_classes", ()) if view_cls else ()
        if not any(issubclass(perm, IsClientAccount) for perm in perms):
            missing.append(route)
    return missing


def test_every_cabinet_route_requires_a_verified_client() -> None:
    """C1: /api/account/* served CRM data to a client who never confirmed the email."""
    assert routes_without_verified_client(cabinet_urls.urlpatterns) == []


def test_verified_client_detector_flags_an_open_view() -> None:
    class OpenView(APIView):
        permission_classes = (AllowAny,)

    assert routes_without_verified_client([path("open/", OpenView.as_view())]) == ["open/"]


# ── Settings ─────────────────────────────────────────────────────────────────

_DOTTED = re.compile(r"^[a-z_][a-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")

# Settings prefix → import name of the package that reads it.
PACKAGE_PREFIXES: dict[str, str] = {
    "AXES_IPWARE_": "ipware",
    "IPWARE_": "ipware",
    "AXES_": "axes",
    "CELERY_": "celery",
    "CORS_": "corsheaders",
    "WHITENOISE_": "whitenoise",
    "SPECTACULAR_": "drf_spectacular",
    "SIMPLE_JWT": "rest_framework_simplejwt",
    "SENTRY_": "sentry_sdk",
    "DEBUG_TOOLBAR_": "debug_toolbar",
    "CKEDITOR_": "ckeditor",
}


def dotted_values(value: Any, where: str) -> Iterator[tuple[str, str]]:
    """Yield ``(where, value)`` for plain strings that look like ``module.attr``."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from dotted_values(item, f"{where}[{key!r}]")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            yield from dotted_values(item, f"{where}[{index}]")
    elif type(value) is str and _DOTTED.match(value):
        yield where, value


def unresolvable(values: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Dotted paths of installed top-level packages that do not import."""
    bad = []
    for where, dotted in values:
        if importlib.util.find_spec(dotted.split(".")[0]) is None:
            continue  # host names, «auth.User» and other non-import strings
        try:
            importlib.import_module(dotted)
            continue
        except ImportError:
            pass
        try:
            import_string(dotted)
        except ImportError:
            bad.append((where, dotted))
    return bad


def test_settings_dotted_paths_import() -> None:
    """H2-class: a setting naming a callable or class that does not exist is silently ignored."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # reading deprecated EMAIL_* settings warns
        values = [
            item
            for name in dir(settings)
            if name.isupper() and name != "UNFOLD"
            for item in dotted_values(getattr(settings, name), name)
        ]
    assert unresolvable(values) == []


def test_unfold_search_models_exist() -> None:
    unfold: dict[str, Any] = settings.UNFOLD
    labels = unfold.get("COMMAND", {}).get("search_models", [])
    missing = []
    for label in labels:
        try:
            apps.get_model(label)
        except LookupError:
            missing.append(label)
    assert labels
    assert missing == []


def test_unresolvable_detector_flags_missing_attribute() -> None:
    assert unresolvable([("X", "config.settings.NO_SUCH_SETTING_CLASS")]) == [
        ("X", "config.settings.NO_SUCH_SETTING_CLASS")
    ]


def settings_without_package(names: Iterable[str]) -> list[tuple[str, str]]:
    """Explicitly set names whose package (by prefix) is not installed."""
    missing = []
    for name in names:
        for prefix, package in PACKAGE_PREFIXES.items():
            if name.startswith(prefix):
                if importlib.util.find_spec(package) is None:
                    missing.append((name, package))
                break
    return missing


def test_settings_for_third_party_packages_have_the_package() -> None:
    """H2: AXES_IPWARE_* were configured while django-ipware was not installed."""
    module = importlib.import_module(os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings"))
    assert settings_without_package(n for n in dir(module) if n.isupper()) == []


def test_package_detector_flags_ipware_settings_without_ipware() -> None:
    if importlib.util.find_spec("ipware") is not None:
        pytest.skip("django-ipware is installed")
    assert settings_without_package(["AXES_IPWARE_PROXY_COUNT"]) == [("AXES_IPWARE_PROXY_COUNT", "ipware")]


# ── Paths in agent instructions ──────────────────────────────────────────────

_PATH_REF = re.compile(
    r"(?<![\w/.-])((?:scripts|_docs|backend|frontend/src|deploy|\.github/workflows|\.cursor/rules)/"
    r"[\w./-]*[\w-]\.(?:sh|py|md|yml|yaml|conf|inc|tsx|ts|mdc|json))(?![\w])"
)


LOCAL_ONLY_DIRS = (".cursor", "_docs")


def instruction_files() -> list[Path]:
    """Files agents follow literally; ``.cursor/rules`` exists only locally."""
    files = [ROOT / "AGENTS.md"]
    for pattern in ("scripts/*.sh", "scripts/*.py", ".github/workflows/*.yml", ".cursor/rules/*.mdc"):
        files.extend(sorted(ROOT.glob(pattern)))
    return [f for f in files if f.is_file()]


def dangling_refs(text: str, root: Path) -> list[str]:
    """Repo-relative paths mentioned in ``text`` that do not exist under ``root``.

    ``.cursor/`` and ``_docs/`` are git-ignored: their references are checked
    only where those folders exist (developer machine), never in CI.
    """
    absent_local = tuple(f"{d}/" for d in LOCAL_ONLY_DIRS if not (root / d).is_dir())
    return sorted(
        {
            ref
            for ref in _PATH_REF.findall(text)
            if not ref.startswith(absent_local or ("\0",)) and not (root / ref).exists()
        }
    )


def test_instruction_files_reference_existing_paths() -> None:
    """M38: rules sent agents to ensure-release-pr.sh and docs/releases.md that did not exist."""
    dangling = {
        str(f.relative_to(ROOT)): refs
        for f in instruction_files()
        if (refs := dangling_refs(f.read_text(encoding="utf-8", errors="ignore"), ROOT))
    }
    assert dangling == {}


def test_local_only_refs_are_checked_only_where_the_folder_exists(tmp_path: Path) -> None:
    text = "See `_docs/releases.md` and `.cursor/rules/no-such.mdc`."
    assert dangling_refs(text, tmp_path) == []
    (tmp_path / "_docs").mkdir()
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    assert dangling_refs(text, tmp_path) == [".cursor/rules/no-such.mdc", "_docs/releases.md"]


def test_dangling_ref_detector_flags_missing_script() -> None:
    text = "Run `scripts/no-such-release.sh`, then see `scripts/pre-commit-checkup.sh`."
    assert dangling_refs(text, ROOT) == ["scripts/no-such-release.sh"]
