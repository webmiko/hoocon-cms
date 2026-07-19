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


class Product(models.Model):
    """Product line/series (groups SKUs).

    Product = линейка (напр. «HVA серия»); SKU = конкретная модель
    (напр. «HVA-5NM»). `category` — обязательная FK с on_delete=PROTECT:
    нельзя удалить категорию, в которой есть товары (защита каталога).

    Args (fields):
        category: FK Category (required). PROTECT — удаление категории
            с товарами блокируется.
        name: человекочитаемое имя линейки, напр. «HVA серия».
        slug: path-сегмент URL, уникален.
        description: опциональное описание для SEO/листинга.
        created_at / updated_at: авто-таймстампы.
    """

    category: models.ForeignKey = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        help_text="Категория товара (обязательная). PROTECT — нельзя удалить.",
    )
    name: models.CharField = models.CharField(max_length=200)
    slug: models.SlugField = models.SlugField(max_length=200, unique=True, db_index=True)
    description: models.TextField = models.TextField(blank=True, default="")
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "продукт"
        verbose_name_plural = "продукты"
        ordering = ("name",)

    def __str__(self) -> str:
        """Return the product name for Admin and logs."""
        return self.name


class SKU(models.Model):
    """Stock-keeping unit — конкретная модель (единица каталога).

    SKU = то, что клиент подбирает и запрашивает (напр. «HVA-5NM»).
    `slug` = канонический path из sitemap Tilda (сохраняем дословно, даже с
    опечатками — см. docs/seo-url-migration.md). `sku_code` = артикул.
    `price` хранится, но в публичный API не утекает (SiteSettings.show_prices).
    `analog_belimo_code` — задел для AnalogMap (P1, docs/market-analysis.md §6.3).

    Args (fields):
        product: FK Product (required). PROTECT — нельзя удалить линейку с SKU.
        name: человекочитаемое имя, напр. «Привод воздушный HVA 5NM».
        slug: канонический URL-путь (уникален), напр. `privod-vozdushniy-hva-5nm`.
        sku_code: артикул (уникален, не пуст), напр. `HVA-5NM` или `BV215`.
        analog_belimo_code: опц. код аналога Belimo (задел для AnalogMap P1).
        price: опц. цена (Decimal); null = по запросу. Скрыт в публичном API.
        description: опц. описание для карточки.
        is_published: видимость в каталоге (default True).
        created_at / updated_at: авто-таймстампы.
    """

    product: models.ForeignKey = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="skus",
        help_text="Продукт/линейка (обязательный). PROTECT — нельзя удалить.",
    )
    name: models.CharField = models.CharField(max_length=300)
    slug: models.SlugField = models.SlugField(max_length=300, unique=True, db_index=True)
    sku_code: models.CharField = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Артикул (уникален, не пуст), напр. HVA-5NM или BV215.",
    )
    analog_belimo_code: models.CharField | None = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        default=None,
        help_text="Код аналога Belimo (задел для AnalogMap P1).",
    )
    price: models.DecimalField | None = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=("Цена для КП менеджеру. В публичный API не утекает (см. SiteSettings.show_prices_on_site)."),
    )
    description: models.TextField = models.TextField(blank=True, default="")
    is_published: models.BooleanField = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Видимость SKU в публичном каталоге.",
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SKU"
        verbose_name_plural = "SKU"
        ordering = ("sku_code",)

    def __str__(self) -> str:
        """Return the SKU name for Admin and logs."""
        return self.name


class Attribute(models.Model):
    """Dictionary entry for a SKU technical attribute (EAV).

    Словарь ТТХ: момент, напряжение, тип управления, пружина… Значения
    хранятся в AttributeValue (одна строка на пару SKU+attribute). EAV даёт
    фильтруемость (Slice 9) без JSONB-магии; см. docs/data-quality-etl.md §4.1.

    Args (fields):
        name: человекочитаемое имя, напр. «Момент».
        slug: ключ фильтра, напр. `moment` (уникален).
        unit: единица измерения, напр. «Н·м», «В»; пусто для безразмерных.
        created_at / updated_at: авто-таймстампы.
    """

    name: models.CharField = models.CharField(max_length=200)
    slug: models.SlugField = models.SlugField(max_length=100, unique=True, db_index=True)
    unit: models.CharField = models.CharField(max_length=50, blank=True, default="")
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "атрибут"
        verbose_name_plural = "атрибуты"
        ordering = ("name",)

    def __str__(self) -> str:
        """Return the attribute name for Admin and logs."""
        return self.name


class AttributeValue(models.Model):
    """Value of an Attribute for a specific SKU (EAV link).

    Одна строка на пару (sku, attribute). `value` хранится строкой —
    фильтры каталога (Slice 9) делают exact match (напр. moment=5).
    Numeric range filtering — P1 (можно добавить value_number позже).

    Args (fields):
        sku: FK SKU (CASCADE — удаление SKU удаляет его ТТХ).
        attribute: FK Attribute (PROTECT — нельзя удалить словарный атрибут,
            если он используется в SKU).
        value: значение как строка, напр. «5», «230», «да».
        created_at / updated_at: авто-таймстампы.
    """

    sku: models.ForeignKey = models.ForeignKey(
        SKU,
        on_delete=models.CASCADE,
        related_name="attribute_values",
    )
    attribute: models.ForeignKey = models.ForeignKey(
        Attribute,
        on_delete=models.PROTECT,
        related_name="values",
    )
    value: models.CharField = models.CharField(max_length=200)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "значение атрибута"
        verbose_name_plural = "значения атрибутов"
        unique_together = (("sku", "attribute"),)
        ordering = ("attribute__name",)

    def __str__(self) -> str:
        """Return 'sku_code / attribute_name = value' for Admin readability."""
        return f"{self.sku.sku_code} / {self.attribute.name} = {self.value}"
