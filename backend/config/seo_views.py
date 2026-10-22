"""Sitemap.xml, robots.txt, and llms.txt generators for SEO.

Spec: ПЛАН §6 Iter 2; БЗ SEO-индексация-SPA.md; docs/seo-url-migration.md
(canonical URLs without trailing slash).
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views import View

from catalog.models import SKU, Category
from catalog.urls_paths import catalog_category_path, catalog_path_for_sku
from config.seo.routes import CANONICAL_REPLACEMENTS, PUBLIC_STATIC_ROUTES
from content.models import Article, News, Page
from content.views import publicly_visible

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
            "Disallow: /rfq",
            "Disallow: /replacement",
            "Disallow: /compare",
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
        f"- [Документация]({base}/dokumentaciya): инструкции и паспорта PDF",
        f"- [Статьи]({base}/statyi): технические материалы по вентиляции и приводам",
        f"- [Новости]({base}/novosti): новости компании",
        f"- [FAQ]({base}/faq): частые вопросы по подбору",
        f"- [Контакты]({base}/kontakty): как связаться",
        "",
        "## Для LLM",
        f"- [Полный контекст]({base}/llms-full.txt): расширенное описание продукта и URL",
        f"- [Краткий индекс (алиас)]({base}/llm.txt): то же, что /llms.txt",
        "",
        "## Разделы каталога",
        *_category_lines(base),
        "",
        "## Аналоги Belimo",
        *_analog_lines(base),
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
        f"- {base}/dokumentaciya — документация (PDF)",
        f"- {base}/statyi — статьи",
        f"- {base}/novosti — новости",
        f"- {base}/faq — FAQ",
        f"- {base}/kontakty — контакты",
        "",
        "## Разделы каталога",
        *_category_lines(base),
        "",
        "## Аналоги Belimo",
        "Один пример на код Belimo. Остальные исполнения — в sitemap.",
        *_analog_lines(base),
        "",
        "## Файлы для LLM",
        f"- {base}/llms.txt — краткий индекс (llmstxt.org)",
        f"- {base}/llm.txt — алиас краткого индекса",
        f"- {base}/llms-full.txt — этот файл",
        "",
    ]
    return "\n".join(lines)


def _category_lines(base: str) -> list[str]:
    """One markdown link per catalog section."""
    return [f"- [{cat.name}]({base}{catalog_category_path(cat.slug)})" for cat in Category.objects.order_by("name")]


def _analog_lines(base: str, *, limit: int = 60) -> list[str]:
    """One published SKU per Belimo code, so an agent can answer a model question."""
    seen: set[str] = set()
    lines: list[str] = []
    skus = (
        SKU.objects.filter(is_published=True)
        .exclude(analog_belimo_code="")
        .exclude(analog_belimo_code__isnull=True)
        .select_related("product__category")
        .order_by("analog_belimo_code", "sku_code")
    )
    for sku in skus:
        code = (sku.analog_belimo_code or "").strip()
        key = code.casefold()
        if not code or key in seen:
            continue
        seen.add(key)
        lines.append(f"- {code} → {sku.sku_code or sku.slug} ({base}{catalog_path_for_sku(sku)})")
        if len(lines) >= limit:
            break
    if not lines:
        lines.append("- Коды аналогов указаны на карточках товаров.")
    return lines


def _lastmod(moment: datetime | None) -> str | None:
    """Sitemap date in the site timezone."""
    if moment is None:
        return None
    if timezone.is_aware(moment):
        moment = timezone.localtime(moment)
    return moment.date().isoformat()


class SitemapXmlView(View):
    """GET /sitemap.xml — canonical URLs without trailing slash."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        """Return sitemap.xml with canonical public URLs."""
        base = _site_base_url(request)
        urls: list[tuple[str, str | None]] = []

        for path in sorted(PUBLIC_STATIC_ROUTES.keys()):
            urls.append((f"{base}{path}" if path != "/" else f"{base}/", None))

        for cat in Category.objects.order_by("slug"):
            urls.append((f"{base}{catalog_category_path(cat.slug)}", _lastmod(cat.updated_at)))

        for sku in SKU.objects.filter(is_published=True).select_related("product__category").order_by("slug"):
            urls.append((f"{base}{catalog_path_for_sku(sku)}", _lastmod(sku.updated_at)))

        for page in publicly_visible(Page).order_by("slug"):
            path = f"/{page.slug}"
            if path in PUBLIC_STATIC_ROUTES or path in CANONICAL_REPLACEMENTS:
                continue
            urls.append((f"{base}{path}", _lastmod(page.updated_at)))

        articles = list(publicly_visible(Article).order_by("slug"))
        article_slugs = {art.slug for art in articles}
        for art in articles:
            urls.append((f"{base}/statyi/{art.slug}", _lastmod(art.updated_at)))

        for news in publicly_visible(News).order_by("slug"):
            mirrored = news.slug.removeprefix("article-") if news.slug.startswith("article-") else ""
            if mirrored and mirrored in article_slugs:
                continue
            urls.append((f"{base}/novosti/{news.slug}", _lastmod(news.updated_at)))

        seen: set[str] = set()
        unique: list[tuple[str, str | None]] = []
        for item in urls:
            if item[0] not in seen:
                seen.add(item[0])
                unique.append(item)

        body = self._render_xml(unique)
        return HttpResponse(body, content_type="application/xml; charset=utf-8")

    @staticmethod
    def _render_xml(urls: list[tuple[str, str | None]]) -> str:
        """Render the sitemap XML from canonical URLs and optional lastmod dates."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<urlset xmlns="{_SITEMAP_NS}">',
        ]
        for url, lastmod in urls:
            lines.append("  <url>")
            lines.append(f"    <loc>{url}</loc>")
            if lastmod:
                lines.append(f"    <lastmod>{lastmod}</lastmod>")
            lines.append("  </url>")
        lines.append("</urlset>")
        return "\n".join(lines) + "\n"
