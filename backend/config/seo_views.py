"""Sitemap.xml, robots.txt, and llms.txt generators for SEO.

Spec: ПЛАН §6 Iter 2; БЗ SEO-индексация-SPA.md; docs/seo-url-migration.md
(canonical URLs without trailing slash).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views import View

from catalog.models import SKU, Category
from catalog.urls_paths import catalog_category_path, catalog_path_for_sku
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
    """GET /llms.txt — curated index for LLM agents (llmstxt.org)."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return llms.txt Markdown content."""
        return HttpResponse(
            _build_llms_txt(_site_base_url(request)),
            content_type="text/plain; charset=utf-8",
        )


class LlmTxtAliasView(LlmsTxtView):
    """GET /llm.txt — alias of /llms.txt."""


class LlmsFullTxtView(View):
    """GET /llms-full.txt — expanded context for LLM agents."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return llms-full.txt Markdown content."""
        return HttpResponse(
            _build_llms_full_txt(_site_base_url(request)),
            content_type="text/plain; charset=utf-8",
        )


def _build_llms_txt(base: str) -> str:
    """Build the short llms.txt index (llmstxt.org shape)."""
    lines = [
        "# Hoocon",
        (
            "> B2B-сайт электроприводов Hoocon для вентиляции и кондиционирования "
            "(HVAC): каталог моделей, документы, статьи и запрос КП (RFQ). "
            "Онлайн-корзины и оплаты в v1 нет."
        ),
        "",
        "Цены на витрине по умолчанию скрыты. Канонические URL без опечаток; устаревшие path с опечатками отдают 301.",
        "",
        "## Основные страницы",
        f"- [Главная]({base}/): обзор ассортимента и вход в каталог",
        f"- [Каталог]({base}/catalog): список продукции с фильтрами по характеристикам",
        f"- [Статьи]({base}/statyi): технические материалы по вентиляции и приводам",
        f"- [Новости]({base}/novosti): новости компании",
        f"- [FAQ]({base}/faq): частые вопросы по подбору",
        f"- [Контакты]({base}/kontakty): как связаться",
        "",
        "## Для LLM",
        f"- [Полный контекст]({base}/llms-full.txt): расширенное описание продукта и URL",
        f"- [Краткий индекс (алиас)]({base}/llm.txt): то же, что /llms.txt",
        "",
        "## Optional",
        f"- [Sitemap]({base}/sitemap.xml): полный список индексируемых URL",
        "",
    ]
    return "\n".join(lines)


def _build_llms_full_txt(base: str) -> str:
    """Build the expanded llms-full.txt companion file."""
    lines = [
        "# Hoocon — полный контекст для LLM",
        ("> Расширенное описание B2B-сайта Hoocon (электроприводы вентиляции / HVAC) для агентов и языковых моделей."),
        "",
        "## Продукт",
        "Hoocon поставляет электроприводы для воздушного клапана, противопожарных "
        "систем и дымоудаления. Клиент — инженер, снабженец или дилер: подобрать "
        "модель по характеристикам, скачать PDF, запросить КП. В v1 нет онлайн-корзины и оплаты.",
        "",
        f"Канонический домен: {base}",
        "",
        "## Канонические URL и редиректы",
        "- Опечатки в старых ЧПУ исправлены; 301 со старых path:",
        f"  - `{base}/privod-protivipozharniy-3nm` → `{base}/privod-protivopozharniy-3nm`",
        f"  - `{base}/privod-vozdushniy-bezpruzhini-uskorenniy-hva-q-5nm` → "
        f"`{base}/privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-5nm`",
        "- Tilda `/tproduct/…` → канонические ЧПУ (см. redirects seed).",
        "",
        "## Ключевые разделы",
        f"- {base}/catalog — каталог",
        f"- {base}/statyi — статьи",
        f"- {base}/novosti — новости",
        f"- {base}/faq — FAQ",
        f"- {base}/kontakty — контакты",
        "",
        "## Файлы для LLM",
        f"- {base}/llms.txt — краткий индекс (llmstxt.org)",
        f"- {base}/llm.txt — алиас краткого индекса",
        f"- {base}/llms-full.txt — этот файл",
        "",
    ]
    return "\n".join(lines)


class SitemapXmlView(View):
    """GET /sitemap.xml — canonical URLs without trailing slash."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return sitemap.xml with canonical public URLs."""
        base = _site_base_url(request)
        urls: list[str] = []

        for path in sorted(PUBLIC_STATIC_ROUTES.keys()):
            urls.append(f"{base}{path}" if path != "/" else f"{base}/")

        for cat in Category.objects.order_by("slug"):
            urls.append(f"{base}{catalog_category_path(cat.slug)}")

        for sku in SKU.objects.filter(is_published=True).select_related("product__category").order_by("slug"):
            urls.append(f"{base}{catalog_path_for_sku(sku)}")

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
