"""Фрагмент settings: Unfold до admin + UNFOLD с бренд-цветами."""

# INSTALLED_APPS = [
#     "unfold",
#     "unfold.contrib.filters",
#     "unfold.contrib.forms",
#     "django.contrib.admin",
#     ...
# ]

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from config.brand_colors import PRIMARY_OKLCH

UNFOLD = {
    "SITE_TITLE": "Project Admin",
    "SITE_HEADER": "Project",
    "SITE_SUBHEADER": "Staff",
    "SITE_URL": "/",
    "THEME": "light",
    "BORDER_RADIUS": "8px",
    "COLORS": {"primary": PRIMARY_OKLCH},
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": _("Навигация"),
                "separator": True,
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                ],
            },
        ],
    },
}
