"""Tests for redirects.Redirect model (TDD: red → green → refactor).

Spec: docs/seo-url-migration.md §3 —
Redirect(from_path unique, to_path, status_code=301, is_active=True).

Покрывает: создание, уникальность from_path, дефолты 301/True,
допустимость 302, __str__. Больший цикл (301 middleware/nginx map) —
в отдельных тестах после Admin/API.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError


@pytest.mark.django_db
def test_create_redirect_with_from_and_to_paths() -> None:
    """Can create a Redirect with from_path and to_path."""
    from redirects.models import Redirect

    redirect = Redirect.objects.create(
        from_path="/tproduct/12345-bv215",
        to_path="/sharovoy-kran-bv215",
    )
    assert redirect.pk is not None
    assert redirect.from_path == "/tproduct/12345-bv215"
    assert redirect.to_path == "/sharovoy-kran-bv215"


@pytest.mark.django_db
def test_from_path_must_be_unique() -> None:
    """Duplicate from_path raises IntegrityError (one canonical target per old URL)."""
    from redirects.models import Redirect

    Redirect.objects.create(from_path="/old-a", to_path="/new-a")
    with pytest.raises(IntegrityError):
        Redirect.objects.create(from_path="/old-a", to_path="/new-b")


@pytest.mark.django_db
def test_default_status_code_is_301() -> None:
    """Default status_code is 301 (permanent) — SEO cutover default."""
    from redirects.models import Redirect

    redirect = Redirect.objects.create(from_path="/a", to_path="/b")
    assert redirect.status_code == 301


@pytest.mark.django_db
def test_default_is_active_is_true() -> None:
    """Default is_active is True (redirect enabled on creation)."""
    from redirects.models import Redirect

    redirect = Redirect.objects.create(from_path="/a", to_path="/b")
    assert redirect.is_active is True


@pytest.mark.django_db
def test_status_code_302_allowed() -> None:
    """Can set status_code to 302 (temporary) for promo/A-B redirects."""
    from redirects.models import Redirect

    redirect = Redirect.objects.create(
        from_path="/a",
        to_path="/b",
        status_code=302,
    )
    assert redirect.status_code == 302


@pytest.mark.django_db
def test_str_shows_from_to_and_status() -> None:
    """__str__ format: 'from → to (status)' for Admin readability."""
    from redirects.models import Redirect

    redirect = Redirect.objects.create(
        from_path="/tproduct/x",
        to_path="/sharovoy-kran-bv215",
    )
    assert str(redirect) == "/tproduct/x → /sharovoy-kran-bv215 (301)"
