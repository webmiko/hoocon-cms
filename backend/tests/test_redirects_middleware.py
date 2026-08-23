"""Tests for typo-slug Redirect seeds, CSV import, and middleware 301."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from redirects.models import Redirect
from redirects.pathutils import normalize_path, validate_internal_path
from redirects.services import load_redirects_from_csv, render_nginx_map

REPO_ROOT = Path(__file__).resolve().parents[2]
TYPO_SEED = REPO_ROOT / "backend/redirects/seeds/redirects-slug-typo-seed.csv"
TPRODUCT_SEED = REPO_ROOT / "backend/redirects/seeds/redirects-tproduct-seed.csv"


def test_normalize_path_strips_trailing_slash() -> None:
    assert normalize_path("/catalog/") == "/catalog"
    assert normalize_path("catalog") == "/catalog"


def test_validate_internal_path_rejects_open_redirect() -> None:
    with pytest.raises(ValidationError):
        validate_internal_path("https://evil.example/phish")
    with pytest.raises(ValidationError):
        validate_internal_path("//evil.example/phish")
    validate_internal_path("/privod-protivopozharniy-3nm")


@pytest.mark.django_db
def test_typo_seed_import_and_middleware_301(client: Client) -> None:
    stats = load_redirects_from_csv(TYPO_SEED)
    assert stats["total"] == 2
    assert stats["created"] == 2

    response = client.get("/privod-protivipozharniy-3nm")
    assert response.status_code == 301
    assert response["Location"] == "/privod-protivopozharniy-3nm"

    response = client.get("/privod-vozdushniy-bezpruzhini-uskorenniy-hva-q-5nm/")
    assert response.status_code == 301
    assert response["Location"] == "/privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-5nm"


@pytest.mark.django_db
def test_tproduct_seed_row_redirects(client: Client) -> None:
    load_redirects_from_csv(TPRODUCT_SEED)
    response = client.get("/tproduct/629593806372-bv215-sharovoi-kran-2-hodovii-dn-15")
    assert response.status_code == 301
    assert response["Location"] == "/sharovoy-kran-bv215"


@pytest.mark.django_db
def test_inactive_redirect_is_ignored(client: Client) -> None:
    Redirect.objects.create(
        from_path="/old-sale",
        to_path="/catalog",
        status_code=301,
        is_active=False,
    )
    response = client.get("/old-sale")
    assert response.status_code != 301
    assert response.status_code != 302
    assert "Location" not in response


@pytest.mark.django_db
def test_render_nginx_map_contains_typo_rules() -> None:
    load_redirects_from_csv(TYPO_SEED)
    body = render_nginx_map(list(Redirect.objects.filter(is_active=True)))
    assert "/privod-protivipozharniy-3nm /privod-protivopozharniy-3nm;" in body


@pytest.mark.django_db
def test_redirect_lookup_reuses_index(django_assert_num_queries) -> None:
    """Lookup loads active redirects once per TTL, not once per path."""
    from redirects.lookup import clear_redirect_index, lookup_redirect

    load_redirects_from_csv(TYPO_SEED)
    clear_redirect_index()

    with django_assert_num_queries(1):
        hit = lookup_redirect("/privod-protivipozharniy-3nm")
        assert hit is not None
        assert lookup_redirect("/no-such-path") is None


@pytest.mark.django_db
def test_redirect_index_invalidates_after_admin_save(client: Client) -> None:
    """New redirect is visible without waiting for TTL."""
    from redirects.lookup import clear_redirect_index

    clear_redirect_index()
    Redirect.objects.create(
        from_path="/fresh-old",
        to_path="/catalog",
        status_code=301,
        is_active=True,
    )
    response = client.get("/fresh-old")
    assert response.status_code == 301
    assert response["Location"] == "/catalog"
