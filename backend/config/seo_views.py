"""Sitemap.xml, robots.txt, and llms.txt generators for SEO.

Spec: ПЛАН §6 Iter 2; БЗ SEO-индексация-SPA.md; docs/seo-url-migration.md
(canonical URLs without trailing slash).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views import View

from catalog.models import SKU
from config.seo.routes import PUBLIC_STATIC_ROUTES
from content.models import Article, News, Page

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _site_base_url(request: HttpRequest) -> str:
    """Return the site base URL (scheme + host), preferring SITE_URL."""
    configured = getattr(settings, "SITE_URL", "") or ""
    if configured.startswith("http"):
        return configured.rstrip("/")
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
            "Disallow: /search",
            "Disallow: /consultation",
            "Disallow: /replacement",
            "",
            f"Sitemap: {_site_base_url(request)}/sitemap.xml",
        ]
        body = "\n".join(lines) + "\n"
        return HttpResponse(body, content_type="text/plain; charset=utf-8")


class LlmsTxtView(View):
    """GET /llms.txt — brief site summary for AI crawlers (optional БЗ)."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return llms.txt content."""
        base = _site_base_url(request)
        lines = [
            "# Hoocon",
            "",
            "> B2B электроприводы ОВК: каталог, паспорта, подбор аналогов Belimo, RFQ.",
            "",
            f"- Каталог: {base}/catalog",
            f"- Статьи: {base}/statyi",
            f"- FAQ: {base}/faq",
            f"- Контакты: {base}/kontakty",
            f"- Sitemap: {base}/sitemap.xml",
            "",
        ]
        return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


class SitemapXmlView(View):
    """GET /sitemap.xml — canonical URLs without trailing slash."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return sitemap.xml with canonical public URLs."""
        base = _site_base_url(request)
        urls: list[str] = []

        for path in sorted(PUBLIC_STATIC_ROUTES.keys()):
            urls.append(f"{base}{path}" if path != "/" else f"{base}/")

        for sku in SKU.objects.filter(is_published=True).order_by("slug"):
            urls.append(f"{base}/{sku.slug}")

        for page in Page.objects.filter(is_published=True).order_by("slug"):
            path = f"/{page.slug}"
            if path not in PUBLIC_STATIC_ROUTES:
                urls.append(f"{base}{path}")

        for art in Article.objects.filter(is_published=True).order_by("slug"):
            urls.append(f"{base}/statyi/{art.slug}")

        for news in News.objects.filter(is_published=True).order_by("slug"):
            urls.append(f"{base}/novosti/{news.slug}")

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique.append(url)

        body = self._render_xml(unique)
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
