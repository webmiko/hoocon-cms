"""App config for staff mobile REST API."""

from django.apps import AppConfig


class StaffApiConfig(AppConfig):
    """Manager Flutter API under ``/api/staff/``."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "staff_api"
    verbose_name = "Staff mobile API"
