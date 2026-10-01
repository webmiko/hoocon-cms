"""App config for staff roles (Groups + permission sync)."""

from django.apps import AppConfig
from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_migrate


def _resync_staff_groups_on_post_migrate(
    sender: object,
    app_config: object = None,
    using: str = DEFAULT_DB_ALIAS,
    **kwargs: object,
) -> None:
    """Re-apply the staff group permission matrix after every migrate run.

    ``post_migrate`` fires once per app config; the final emission happens
    after all permissions exist, so the idempotent sync leaves groups in the
    desired state without a manual ``sync_staff_groups`` call.
    """
    if using != DEFAULT_DB_ALIAS:
        return
    from accounts.services import ensure_staff_groups

    ensure_staff_groups()


class AccountsConfig(AppConfig):
    """Staff Groups: Админ / Менеджер / Аналитик."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Учётные записи / роли"

    def ready(self) -> None:
        """Install Admin Email OTP + passkey routes/login patch."""
        from accounts.passkey_views import install_admin_passkeys
        from config.admin_otp_views import install_admin_email_otp

        install_admin_email_otp()
        install_admin_passkeys()
        post_migrate.connect(
            _resync_staff_groups_on_post_migrate,
            dispatch_uid="accounts.resync_staff_groups",
        )
