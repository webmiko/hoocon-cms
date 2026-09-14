"""Tests for staff Wiki admin (browse + read HTML)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from content.models import WikiDocument

User = get_user_model()


@pytest.mark.django_db
def test_wiki_browse_page_for_superuser(client) -> None:
    """Staff with view_wikidocument sees Wiki index grouped by category."""
    admin_user = User.objects.create_superuser(
        username="wiki-admin",
        email="wiki-admin@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Тестовый отчёт",
        slug="test-report",
        category="Аналитика склада",
        summary="Пояснение к цифрам.",
        body="<p>42</p>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_browse")
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "Вики" in html
    assert "Тестовый отчёт" in html
    assert "Аналитика склада" in html
    assert "Пояснение к цифрам" in html


@pytest.mark.django_db
def test_wiki_read_full_html_document(client) -> None:
    """Full HTML documents are returned as-is for staff read view."""
    admin_user = User.objects.create_superuser(
        username="wiki-read",
        email="wiki-read@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Dashboard",
        slug="dash-full",
        body="<!DOCTYPE html><html><body><h1>Stock</h1></body></html>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_read", args=["dash-full"])
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert "<h1>Stock</h1>" in response.content.decode()


@pytest.mark.django_db
def test_wiki_read_fragment_uses_admin_wrapper(client) -> None:
    """HTML fragments render inside admin read template with |safe body."""
    admin_user = User.objects.create_superuser(
        username="wiki-frag",
        email="wiki-frag@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Фрагмент",
        slug="frag",
        body="<p>Фрагмент Wiki</p>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_read", args=["frag"])
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-wiki-read__body" in html
    assert "Фрагмент Wiki" in html


@pytest.mark.django_db
def test_csp_wiki_read_allows_inline_scripts_for_dashboards(client) -> None:
    """Wiki read CSP allows inline Chart.js bootstrap (staff HTML dashboards)."""
    admin_user = User.objects.create_superuser(
        username="wiki-csp",
        email="wiki-csp@example.com",
        password="password12",
    )
    WikiDocument.objects.create(
        title="Dashboard",
        slug="dash-csp",
        body="<!DOCTYPE html><html><body><script>window.ok=1</script></body></html>",
    )
    client.force_login(admin_user)
    url = reverse("admin:content_wikidocument_read", args=["dash-csp"])
    response = client.get(url)
    csp = (
        response.headers.get("Content-Security-Policy")
        or response.headers.get("Content-Security-Policy-Report-Only")
        or ""
    )
    assert response.status_code == 200
    assert "'unsafe-inline'" in csp


@pytest.mark.django_db
def test_wiki_stock_fixture_uses_self_hosted_chart_js() -> None:
    """Stock dashboard fixture loads Chart.js from static (CSP script-src 'self')."""
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "content" / "fixtures" / "wiki" / "stock-dashboard-14-09-2026.html"
    html = fixture.read_text(encoding="utf-8")
    assert "/static/admin/js/vendor/chart-4.4.4.umd.min.js" in html
    assert "cdn.jsdelivr.net" not in html

    chart_js = Path(__file__).resolve().parents[1] / "static" / "admin" / "js" / "vendor" / "chart-4.4.4.umd.min.js"
    assert chart_js.is_file()
    assert "Chart" in chart_js.read_text(encoding="utf-8", errors="ignore")[:500]


@pytest.mark.django_db
def test_wiki_browse_requires_permission(client) -> None:
    """User without content.view_wikidocument cannot open Wiki browse."""
    user = User.objects.create_user(
        username="no-wiki",
        email="no-wiki@example.com",
        password="password12",
        is_staff=True,
    )
    client.force_login(user)
    url = reverse("admin:content_wikidocument_browse")
    response = client.get(url)
    assert response.status_code == 403
