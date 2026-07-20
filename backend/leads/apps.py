from django.apps import AppConfig


class LeadsConfig(AppConfig):
    """Заявки RFQ / консультация / подбор замены."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "leads"
    verbose_name = "Заявки"
