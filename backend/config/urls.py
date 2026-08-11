"""URL configuration for Hoocon CMS."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

import config.admin_branding  # noqa: F401 — site_header / site_title
from config.admin_pwa import AdminPwaManifestView
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


def _openapi_access(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """DEBUG: open docs; otherwise staff login required (checked per request)."""

    @wraps(view)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if settings.DEBUG:
            return view(request, *args, **kwargs)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_active and request.user.is_staff):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return _wrapped


urlpatterns = [
    # Before admin.site.urls so /admin/manifest.webmanifest is not swallowed.
    path(
        "admin/manifest.webmanifest",
        AdminPwaManifestView.as_view(),
        name="admin-pwa-manifest",
    ),
    path("admin/", admin.site.urls),
    path("api/catalog/", include("catalog.urls")),
    path("api/content/", include("content.urls")),
    path("api/leads/", include("leads.urls")),
    path("api/support/", include("supportchat.urls")),
    path("api/webpush/", include("webpush.urls")),
    path("api/settings/", include("sitesettings.urls")),
    path("api/integrations/", include("social.urls")),
    path("api/", include("search.urls")),
    path("api/health/", HealthView.as_view(), name="api-health"),
    path("api/csrf/", CsrfTokenView.as_view(), name="api-csrf"),
    path("api/schema/", _openapi_access(SpectacularAPIView.as_view()), name="schema"),
    path(
        "api/docs/",
        _openapi_access(SpectacularSwaggerView.as_view(url_name="schema")),
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
