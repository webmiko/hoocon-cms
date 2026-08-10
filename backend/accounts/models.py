"""Staff account extensions (recovery codes for superuser break-glass)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SuperuserRecoveryCode(models.Model):
    """Hashed one-time recovery code for superuser Admin break-glass login.

    Plaintext is shown once at generation; only ``code_hash`` is stored.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recovery_codes",
        verbose_name=_("Пользователь"),
    )
    code_hash = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name=_("Хеш кода"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Создан"),
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Использован"),
    )

    class Meta:
        verbose_name = _("Резервный код супер-админа")
        verbose_name_plural = _("Резервные коды супер-админа")
        indexes = [
            models.Index(fields=["user", "used_at"], name="accounts_rec_user_used_idx"),
        ]

    def __str__(self) -> str:
        status = "used" if self.used_at else "unused"
        return f"RecoveryCode(user={self.user_id}, {status})"

    @property
    def is_used(self) -> bool:
        """True after successful consume."""
        return self.used_at is not None
