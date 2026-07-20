"""URL configuration for Hoocon CMS."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.csrf_views import CsrfTokenView
from config.health_views import HealthView
from config.seo.spa_index import spa_index_view
from config.seo_views import (
    LlmsFullTxtView,
    LlmsTxtView,
    LlmTxtAliasView,
    RobotsTxtView,
    SitemapXmlView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/catalog/", include("catalog.urls")),
    path("api/content/", include("content.urls")),
    path("api/leads/", include("leads.urls")),
    path("api/", include("search.urls")),
    path("api/health/", HealthView.as_view(), name="api-health"),
    path("api/csrf/", CsrfTokenView.as_view(), name="api-csrf"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("robots.txt", RobotsTxtView.as_view(), name="robots-txt"),
    path("sitemap.xml", SitemapXmlView.as_view(), name="sitemap-xml"),
    path("llms.txt", LlmsTxtView.as_view(), name="llms-txt"),
    path("llm.txt", LlmTxtAliasView.as_view(), name="llm-txt"),
    path("llms-full.txt", LlmsFullTxtView.as_view(), name="llms-full-txt"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# SPA catch-all last: server-side SEO head (БЗ SEO-индексация-SPA.md).
urlpatterns += [
    re_path(
        r"^(?!api/|admin/|media/|static/).*$",
        spa_index_view,
        name="spa-index",
    ),
]
