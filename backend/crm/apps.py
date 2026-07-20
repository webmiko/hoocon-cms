"""CRM for managers: clients, activities, outbound email from Admin."""

from django.apps import AppConfig


class CrmConfig(AppConfig):
    """CRM: клиенты и почта для менеджеров."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "crm"
    verbose_name = "CRM / клиенты"

    def ready(self) -> None:
        """Import signal handlers."""
        from crm import signals  # noqa: F401
