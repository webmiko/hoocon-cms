"""URL configuration for Hoocon CMS."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.health_views import HealthView
from config.seo_views import RobotsTxtView, SitemapXmlView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/catalog/", include("catalog.urls")),
    path("api/health/", HealthView.as_view(), name="api-health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("robots.txt", RobotsTxtView.as_view(), name="robots-txt"),
    path("sitemap.xml", SitemapXmlView.as_view(), name="sitemap-xml"),
]
