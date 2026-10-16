"""App config for manager requests."""

from django.apps import AppConfig


class StaffRequestsConfig(AppConfig):
    """Техподдержка: запросы менеджеров к администратору."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "staffrequests"
    verbose_name = "Техподдержка"
