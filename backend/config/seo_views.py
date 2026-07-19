"""Sitemap.xml and robots.txt generators for SEO.

Spec: ПЛАН §6 Iter 2 — sitemap.xml (only canonical paths, no /tproduct/,
no query filters); robots.txt (Disallow /tilda/, /admin/).
docs/seo-url-migration.md (canonical URLs only).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.views import View

from catalog.models import SKU, Category, Product

# Sitemap 0.9 namespace.
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _site_base_url(request: HttpRequest) -> str:
    """Return the site base URL (scheme + host)."""
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}"


class RobotsTxtView(View):
    """GET /robots.txt — allow catalog, disallow admin/tilda/api."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return robots.txt content."""
        lines = [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /tilda/",
            "Disallow: /api/",
            "",
            f"Sitemap: {_site_base_url(request)}/sitemap.xml",
        ]
        body = "\n".join(lines) + "\n"
        return HttpResponse(body, content_type="text/plain; charset=utf-8")


class SitemapXmlView(View):
    """GET /sitemap.xml — canonical URLs for published catalog content."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return sitemap.xml with canonical category/product/SKU URLs."""
        base = _site_base_url(request)
        urls: list[str] = []

        # Category list page (canonical /catalog/).
        urls.append(f"{base}/catalog/")

        # Category pages (by slug).
        for cat in Category.objects.all().order_by("slug"):
            urls.append(f"{base}/catalog/{cat.slug}/")

        # Product pages (by slug, under their category).
        for prod in Product.objects.select_related("category").order_by("slug"):
            urls.append(f"{base}/catalog/{prod.category.slug}/{prod.slug}/")  # type: ignore[attr-defined]

        # SKU pages (by slug, published only — no /tproduct/, no query filters).
        for sku in SKU.objects.filter(is_published=True).select_related("product__category").order_by("slug"):
            urls.append(f"{base}/{sku.slug}/")

        body = self._render_xml(urls)
        return HttpResponse(body, content_type="application/xml; charset=utf-8")

    @staticmethod
    def _render_xml(urls: list[str]) -> str:
        """Render the sitemap XML from a list of canonical URLs."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<urlset xmlns="{_SITEMAP_NS}">',
        ]
        for url in urls:
            lines.append("  <url>")
            lines.append(f"    <loc>{url}</loc>")
            lines.append("  </url>")
        lines.append("</urlset>")
        return "\n".join(lines) + "\n"
