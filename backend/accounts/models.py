"""Staff account extensions (recovery codes + WebAuthn passkeys) + client cabinet auth."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
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


class PasskeyCredential(models.Model):
    """WebAuthn passkey for passwordless Admin login (staff only)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="passkeys",
        verbose_name=_("Пользователь"),
    )
    credential_id = models.CharField(
        max_length=512,
        unique=True,
        verbose_name=_("Идентификатор ключа"),
    )
    public_key = models.BinaryField(verbose_name=_("Публичный ключ"))
    sign_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Счётчик подписей"),
    )
    device_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Название устройства"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Создан"),
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Последний вход"),
    )

    class Meta:
        verbose_name = _("Ключ доступа")
        verbose_name_plural = _("Ключи доступа")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "-created_at"], name="accounts_pk_user_created_idx"),
        ]

    def __str__(self) -> str:
        label = self.device_name or self.credential_id[:12]
        return f"Passkey({self.user_id}, {label})"


class StaffTelegramProfile(models.Model):
    """Personal Telegram DM destination for staff alerts (not the announce channel)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_profile",
        verbose_name=_("Пользователь"),
    )
    telegram_chat_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("ID чата Telegram"),
        help_text=_(
            "Числовой ID личного чата с ботом. В личке бота отправьте команду "
            "для получения ID и скопируйте ответ сюда."
        ),
    )
    telegram_alerts_enabled = models.BooleanField(
        default=True,
        verbose_name=_("уведомления в Telegram включены"),
        help_text=_("Выкл — не слать личные уведомления этому сотруднику."),
    )

    class Meta:
        verbose_name = _("Telegram сотрудника")
        verbose_name_plural = _("Telegram сотрудников")

    def __str__(self) -> str:
        chat = (self.telegram_chat_id or "").strip() or "—"
        return f"TG({self.user_id}, {chat})"


class StaffMaxProfile(models.Model):
    """Personal MAX DM destination for staff alerts."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="max_profile",
        verbose_name=_("Пользователь"),
    )
    max_user_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("ID пользователя в MAX"),
        help_text=_(
            "Числовой идентификатор из личного чата с ботом. В боте отправьте /chatid и скопируйте ответ сюда."
        ),
    )
    max_alerts_enabled = models.BooleanField(
        default=True,
        verbose_name=_("уведомления в MAX включены"),
        help_text=_("Выкл — не слать личные уведомления этому сотруднику."),
    )

    class Meta:
        verbose_name = _("MAX сотрудника")
        verbose_name_plural = _("MAX сотрудников")

    def __str__(self) -> str:
        uid = (self.max_user_id or "").strip() or "—"
        return f"MAX({self.user_id}, {uid})"


class StaffMailbox(models.Model):
    """Personal mailbox of a staff user — IMAP fetch + SMTP send.

    Как Telegram/MAX-профили: менеджер заполняет ящик на своей странице
    пользователя. Пароль — пароль приложения Яндекс 360 (один и тот же
    работает и для IMAP, и для SMTP); хранится в БД открытым текстом,
    в форме не отображается (PasswordInput).
    Поля last_* — курсор и здоровье фетчера по этому ящику.
    Пустой ``smtp_host`` — исходящие уходят через общий env-SMTP.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mailbox",
        verbose_name=_("Пользователь"),
    )
    imap_user = models.EmailField(
        _("адрес ящика"),
        blank=True,
        default="",
        help_text=_("Например ivan@hoocon.ru — совпадает с IMAP-логином."),
    )
    imap_password = models.CharField(
        _("пароль приложения IMAP"),
        max_length=200,
        blank=True,
        default="",
        help_text=_("Яндекс 360: Пароль → Пароли приложений → Почта. Оставьте пустым — старый пароль сохранится."),
    )
    folder = models.CharField(
        _("папка"),
        max_length=100,
        default="INBOX",
    )
    smtp_host = models.CharField(
        _("SMTP-сервер"),
        max_length=200,
        blank=True,
        default="smtp.yandex.ru",
        help_text=_("Пусто — исходящие уходят через общий ящик. Логин и пароль те же, что у IMAP."),
    )
    smtp_port = models.PositiveSmallIntegerField(
        _("SMTP-порт"),
        default=465,
    )
    smtp_use_ssl = models.BooleanField(
        _("SMTP по SSL"),
        default=True,
        help_text=_("Вкл — SSL (порт 465), выкл — STARTTLS (порт 587)."),
    )
    is_enabled = models.BooleanField(
        _("включён"),
        default=True,
        help_text=_("Выкл — ящик не опрашивается фетчером и не используется для отправки."),
    )
    last_uid = models.PositiveBigIntegerField(
        _("последний обработанный UID"),
        default=0,
    )
    last_run_at = models.DateTimeField(
        _("последний запуск"),
        null=True,
        blank=True,
    )
    last_error = models.CharField(
        _("последняя ошибка"),
        max_length=300,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлён"))

    class Meta:
        verbose_name = _("Почта сотрудника (IMAP)")
        verbose_name_plural = _("Почта сотрудников (IMAP)")

    def __str__(self) -> str:
        addr = (self.imap_user or "").strip() or "—"
        return f"IMAP({self.user_id}, {addr})"


class StaffVpbxProfile(models.Model):
    """Mango VPBX binding of a staff user — internal extension + toggle."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vpbx_profile",
        verbose_name=_("Пользователь"),
    )
    extension = models.CharField(
        _("добавочный номер"),
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Внутренний номер в Mango АТС — по нему звонок привязывается к менеджеру."),
    )
    is_enabled = models.BooleanField(
        _("включён"),
        default=True,
        help_text=_("Выкл — звонки на этот добавочный не привязываются к сотруднику."),
    )

    class Meta:
        verbose_name = _("Добавочный сотрудника (Mango)")
        verbose_name_plural = _("Добавочные сотрудников (Mango)")

    def __str__(self) -> str:
        ext = (self.extension or "").strip() or "—"
        return f"VPBX({self.user_id}, {ext})"


class ClientAuthMode(models.TextChoices):
    """How a client signs in (A/B modes from plan-client-auth)."""

    PASSWORD = "password", "пароль"
    OTP_EMAIL = "otp_email", "код на почту"
    YANDEX = "yandex", "Яндекс ID"


class ClientAccount(models.Model):
    """Client cabinet login — separate from staff ``auth.User``.

    Session-based: after login the account id is stored in the Django
    session (``config.client_auth``). Password accounts keep a Django
    hash; OTP-only and Yandex-linked accounts use unusable password.
    """

    email = models.EmailField(_("эл. почта"), unique=True, db_index=True)
    password_hash = models.CharField(
        _("хеш пароля"),
        max_length=200,
        blank=True,
        default="",
        help_text=_("Пусто — вход только по коду на почту или Яндекс ID."),
    )
    auth_mode = models.CharField(
        _("способ входа"),
        max_length=20,
        choices=ClientAuthMode.choices,
        default=ClientAuthMode.PASSWORD,
    )
    name = models.CharField(_("имя / контакт"), max_length=200, blank=True, default="")
    phone = models.CharField(_("телефон"), max_length=50, blank=True, default="")
    is_active = models.BooleanField(_("активен"), default=True, db_index=True)
    email_verified_at = models.DateTimeField(
        _("почта подтверждена"),
        null=True,
        blank=True,
        help_text=_("OTP-вход или письмо-подтверждение; Яндекс ID подтверждает сам."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлён"))

    class Meta:
        verbose_name = _("аккаунт клиента")
        verbose_name_plural = _("аккаунты клиентов")
        ordering = ("email",)

    def __str__(self) -> str:
        return self.email

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normalize email to lowercase (identity key)."""
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def set_password(self, raw: str) -> None:
        """Hash and store a password (Django hasher)."""
        self.password_hash = make_password(raw)

    def check_password(self, raw: str) -> bool:
        """True when ``raw`` matches the stored hash."""
        if not self.password_hash:
            return False
        return check_password(raw, self.password_hash)

    def has_usable_password(self) -> bool:
        """True when a password hash is stored."""
        return bool(self.password_hash)

    @property
    def is_authenticated(self) -> bool:
        """DRF duck-type: a resolved cabinet session account is authenticated."""
        return True

    @property
    def is_anonymous(self) -> bool:
        """DRF duck-type counterpart of ``is_authenticated``."""
        return False


class SocialAccount(models.Model):
    """OAuth identity linked to a ClientAccount (задел под Яндекс ID).

    Table exists from auth MVP so mode C does not need a schema migration:
    rows appear when ``YANDEX_OAUTH_ENABLED`` turns on.
    """

    account = models.ForeignKey(
        ClientAccount,
        on_delete=models.CASCADE,
        related_name="social_accounts",
        verbose_name=_("аккаунт"),
    )
    provider = models.CharField(_("провайдер"), max_length=30, db_index=True)
    provider_user_id = models.CharField(_("id у провайдера"), max_length=200)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))

    class Meta:
        verbose_name = _("соцпривязка клиента")
        verbose_name_plural = _("соцпривязки клиентов")
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "provider_user_id"),
                name="accounts_social_provider_uid_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_user_id}"
