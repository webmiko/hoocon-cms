"""App config for staff roles (Groups + permission sync)."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Staff Groups: Админ / Менеджер / Аналитик."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Учётные записи / роли"

    def ready(self) -> None:
        """Install Admin Email OTP routes/login patch (flag-gated at runtime)."""
        from config.admin_otp_views import install_admin_email_otp

        install_admin_email_otp()
