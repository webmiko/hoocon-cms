"""Catalog models for Hoocon CMS (HVAC actuators).

Spec: ПЛАН §6 Iter 1; docs/readiness-backend-ux.md §2.2 —
Category (tree, slug), Product, SKU, Attribute, ProductFile.

Категории по применению: воздух / ПБ / дым / краны.
slug = path-сегмент канонического URL (сохраняем из sitemap Tilda).
"""

from __future__ import annotations

from django.db import models


class Category(models.Model):
    """Product category (self-referential tree).

    Верхний уровень — применения (воздух / ПБ / дым / краны); дочерние —
    серии/подкатегории. `slug` уникален и используется в URL path.

    Args (fields):
        name: человекочитаемое имя, напр. «Воздушные приводы».
        slug: path-сегмент URL, напр. `vozdushnie` (сохраняем из sitemap).
        parent: FK на родительскую категорию (None для корня дерева).
        description: опциональное описание для SEO/листинга категории.
        created_at / updated_at: авто-таймстампы.
    """

    name: models.CharField = models.CharField(max_length=200)
    slug: models.SlugField = models.SlugField(max_length=200, unique=True, db_index=True)
    parent: models.ForeignKey = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Родительская категория (None для корня дерева).",
    )
    description: models.TextField = models.TextField(blank=True, default="")
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "категория"
        verbose_name_plural = "категории"
        ordering = ("name",)

    def __str__(self) -> str:
        """Return the human-readable name for Admin and logs."""
        return self.name
