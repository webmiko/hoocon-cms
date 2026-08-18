"""Tests for CSP middleware (Content-Security-Policy header).

Spec: ПЛАН §6 Iter 4 — F10 (CSP draft); docs/security-baseline.md §CSP.
"""

from __future__ import annotations

import pytest
from django.test import Client


def _csp_value(response) -> str:
    """Return enforced or report-only CSP header value."""
    return (
        response.headers.get("Content-Security-Policy")
        or response.headers.get("Content-Security-Policy-Report-Only")
        or ""
    )


@pytest.mark.django_db
def test_csp_header_present_on_html_response() -> None:
    """Every response carries a Content-Security-Policy header."""
    client = Client()
    response = client.get("/")
    assert _csp_value(response)


@pytest.mark.django_db
def test_csp_header_present_on_api_response() -> None:
    """API responses also carry CSP (defense-in-depth)."""
    client = Client()
    response = client.get("/api/health/")
    assert _csp_value(response)


@pytest.mark.django_db
def test_csp_object_src_none() -> None:
    """CSP forbids object/embed/applet (object-src 'none')."""
    client = Client()
    response = client.get("/api/health/")
    assert "object-src 'none'" in _csp_value(response)


@pytest.mark.django_db
def test_csp_frame_ancestors_none() -> None:
    """CSP forbids framing (frame-ancestors 'none' — clickjacking)."""
    client = Client()
    response = client.get("/api/health/")
    assert "frame-ancestors 'none'" in _csp_value(response)


@pytest.mark.django_db
def test_csp_default_src_self() -> None:
    """CSP default-src 'self' — restricts all resource types to same origin."""
    client = Client()
    response = client.get("/api/health/")
    assert "default-src 'self'" in _csp_value(response)


@pytest.mark.django_db
def test_csp_base_uri_self() -> None:
    """CSP base-uri 'self' — prevents <base> tag hijacking."""
    client = Client()
    response = client.get("/api/health/")
    assert "base-uri 'self'" in _csp_value(response)


@pytest.mark.django_db
def test_csp_includes_font_sources() -> None:
    """CSP allows fonts from 'self' and data: (for @fontsource)."""
    client = Client()
    response = client.get("/api/health/")
    csp = _csp_value(response)
    assert "font-src" in csp
    assert "'self'" in csp


@pytest.mark.django_db
def test_csp_includes_img_data_uri() -> None:
    """CSP allows images from 'self' and data: (placeholders / analytics)."""
    client = Client()
    response = client.get("/api/health/")
    csp = _csp_value(response)
    img_src = next(part.strip() for part in csp.split(";") if part.strip().startswith("img-src"))
    assert "data:" in img_src
    assert "blob:" not in img_src


@pytest.mark.django_db
def test_csp_includes_style_sources() -> None:
    """CSP allows styles from 'self' (CSS modules) and 'unsafe-inline' (Helmet)."""
    client = Client()
    response = client.get("/api/health/")
    assert "style-src" in _csp_value(response)


@pytest.mark.django_db
def test_csp_connect_src_self() -> None:
    """CSP connect-src 'self' — fetch/XHR only to same origin (API proxy)."""
    client = Client()
    response = client.get("/api/health/")
    assert "connect-src 'self'" in _csp_value(response)


@pytest.mark.django_db
def test_csp_html_includes_nonce() -> None:
    """SPA HTML CSP includes a per-request script nonce."""
    client = Client()
    response = client.get("/")
    csp = _csp_value(response)
    assert "nonce-" in csp
    assert 'name="csp-nonce"' in response.content.decode()


@pytest.mark.django_db
def test_csp_disabled_in_debug() -> None:
    """When DJANGO_DEBUG=True, CSP is report-only (dev-friendly)."""
    from django.test import override_settings

    with override_settings(DEBUG=True):
        client = Client()
        response = client.get("/api/health/")
        assert "Content-Security-Policy-Report-Only" in response.headers


@pytest.mark.django_db
def test_csp_admin_allows_unsafe_eval_for_alpine() -> None:
    """Admin CSP allows unsafe-eval so Unfold Alpine x-data can run."""
    client = Client()
    response = client.get("/admin/login/")
    csp = _csp_value(response)
    assert "'unsafe-eval'" in csp
    assert "script-src" in csp


@pytest.mark.django_db
def test_csp_public_html_forbids_unsafe_eval() -> None:
    """Public SPA CSP stays without unsafe-eval."""
    client = Client()
    response = client.get("/")
    assert "'unsafe-eval'" not in _csp_value(response)
