"""Redirect model for SEO URL migration (Tilda → Hoocon CMS).

Spec: docs/seo-url-migration.md §3. Хранит карту 301 со старых URL
(напр. `/tproduct/...-bv215-...`) на канонические ЧПУ (`/sharovoy-kran-bv215`).
На prod отдаётся через nginx map (Iter 5); здесь — единый источник правды.
"""

from __future__ import annotations

from django.db import models


class Redirect(models.Model):
    """A permanent/temporary redirect from `from_path` to `to_path`.

    `from_path` is unique: один старый URL → один канон. `status_code`
    по умолчанию 301 (SEO cutover); 302 — для временных A/B/промо.

    Args (fields):
        from_path: старый path (с leading slash), напр. `/tproduct/12345-bv215`.
        to_path: канонический path, напр. `/sharovoy-kran-bv215`.
        status_code: 301 (default) или 302.
        is_active: включён ли редирект (можно выключать не удаляя).
        created_at / updated_at: авто-таймстампы.
    """

    HTTP_MOVED_PERMANENTLY = 301
    HTTP_FOUND = 302

    STATUS_CHOICES = (
        (HTTP_MOVED_PERMANENTLY, "301 — постоянно"),
        (HTTP_FOUND, "302 — временно"),
    )

    from_path: models.CharField = models.CharField(
        "откуда",
        max_length=512,
        unique=True,
        db_index=True,
        help_text="Старый URL с ведущим слэшем, напр. /tproduct/12345-bv215.",
    )
    to_path: models.CharField = models.CharField(
        "куда",
        max_length=512,
        help_text="Канонический path, напр. /sharovoy-kran-bv215.",
    )
    status_code: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        "код ответа",
        choices=STATUS_CHOICES,
        default=HTTP_MOVED_PERMANENTLY,
        help_text="301 (постоянный, по умолчанию) или 302 (временный).",
    )
    is_active: models.BooleanField = models.BooleanField(
        "активен",
        default=True,
        db_index=True,
        help_text="Можно выключить редирект без удаления записи.",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "редирект"
        verbose_name_plural = "редиректы"
        ordering = ("from_path",)

    def __str__(self) -> str:
        """Return 'from → to (status)' for Admin and logs."""
        return f"{self.from_path} → {self.to_path} ({self.status_code})"
