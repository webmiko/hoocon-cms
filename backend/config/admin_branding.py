"""Django Admin branding and Russian labels for Hoocon CMS."""

from __future__ import annotations

from django.apps import apps
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

admin.site.site_header = _("Hoocon — администрирование")
admin.site.site_title = _("Админка Hoocon")
admin.site.index_title = _("Панель управления")

# Сторонние apps/модели без полной RU-локали — подписи для индекса Admin.
_THIRD_PARTY_APP_NAMES: dict[str, str] = {
    "axes": "Защита входа",
    "django_celery_beat": "Периодические задачи",
    "django_filters": "Фильтры",
}

_THIRD_PARTY_MODEL_NAMES: dict[str, tuple[str, str]] = {
    "axes.AccessAttemptExpiration": (
        "срок попытки доступа",
        "сроки попыток доступа",
    ),
    "django_celery_beat.CrontabSchedule": (
        "расписание crontab",
        "расписания crontab",
    ),
    "django_celery_beat.PeriodicTasks": (
        "трекер периодических задач",
        "трекеры периодических задач",
    ),
}


def localize_third_party_admin() -> None:
    """Override English app/model labels for axes and celery-beat.

    Call after Django apps are ready (imported from urls / AppConfig.ready).
    """
    for label, name in _THIRD_PARTY_APP_NAMES.items():
        try:
            apps.get_app_config(label).verbose_name = name
        except LookupError:
            continue

    for model_label, (singular, plural) in _THIRD_PARTY_MODEL_NAMES.items():
        try:
            model = apps.get_model(model_label)
        except LookupError:
            continue
        model._meta.verbose_name = singular
        model._meta.verbose_name_plural = plural


localize_third_party_admin()
