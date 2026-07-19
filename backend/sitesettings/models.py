"""SiteSettings singleton — глобальные настройки сайта (флаг показа цен и др.).

Spec: ПЛАН §6 Iter 1; docs/security-baseline.md §3.2 (цены скрыты по умолчанию).
Паттерн singleton: ровно одна строка с pk=1. Доступ — через SiteSettings.load().
"""

from __future__ import annotations

from django.db import models


class SiteSettings(models.Model):
    """Singleton site-wide settings.

    Единственная строка (pk=1) хранит флаги, влияющие на публичный API и UI.
    `show_prices_on_site` — security-critical: по умолчанию False (цены скрыты);
    сериализатор каталога отдаёт цену только если True.

    Использование:
        settings = SiteSettings.load()
        if settings.show_prices_on_site: ...
    """

    SINGLETON_PK = 1

    show_prices_on_site: models.BooleanField = models.BooleanField(
        default=False,
        help_text=(
            "Показывать цены в публичном API/UI. По умолчанию False — "
            "цены скрыты (политика RFQ). См. docs/security-baseline.md §3.2."
        ),
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "настройки сайта"
        verbose_name_plural = "настройки сайта"

    @classmethod
    def load(cls) -> SiteSettings:
        """Return the singleton row, creating it with defaults if missing."""
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj

    def save(self, *args: object, **kwargs: object) -> None:
        """Force pk=1 and switch to UPDATE if singleton already exists.

        Без переключения _state.adding новый экземпляр с pk=1 делает INSERT
        и падает на UNIQUE pk. При UPDATE-пути auto_now_add не срабатывает,
        поэтому сохраняем created_at из существующей строки (иначе NOT NULL).
        """
        self.pk = self.SINGLETON_PK
        existing = type(self).objects.filter(pk=self.SINGLETON_PK).first()
        if existing is not None:
            self._state.adding = False
            self.created_at = existing.created_at
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> None:
        """Prevent deletion — singleton must always exist."""
        raise RuntimeError(
            "SiteSettings is a singleton and cannot be deleted.",
        )

    def __str__(self) -> str:
        """Return 'SiteSettings (show_prices_on_site=<state>)' for Admin/logs."""
        return f"SiteSettings (show_prices_on_site={self.show_prices_on_site})"
