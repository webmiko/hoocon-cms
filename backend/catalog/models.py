"""Catalog models for Hoocon CMS (HVAC actuators).

Spec: ПЛАН §6 Iter 1; docs/readiness-backend-ux.md §2.2 —
Category (tree, slug), Product, SKU, Attribute, ProductFile.

Категории приводов — по спецификации модельного ряда
(``catalog.series_categories``); плюс одна корзина для шаровых кранов.
slug = path-сегмент канонического URL.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.contrib.postgres.search import SearchVectorField
from django.db import models

from catalog.validators import (
    sanitize_upload_filename,
    validate_image_upload,
    validate_pdf_upload,
)


def product_file_upload_to(instance: ProductFile, filename: str) -> str:
    """Store under product_files/<sku_id>/<uuid>_<safe_basename>.

    UUID в имени — не угадывать URL; basename проходит sanitize.
    """
    safe = sanitize_upload_filename(filename)
    sku_part = instance.sku_id if instance.sku_id is not None else "pending"
    return f"product_files/{sku_part}/{uuid.uuid4().hex}_{safe}"


def product_image_upload_to(instance: ProductImage, filename: str) -> str:
    """Store under product_images/<sku_id>/<uuid>_<safe_basename>.webp."""
    safe = sanitize_upload_filename(filename)
    sku_part = instance.sku_id if instance.sku_id is not None else "pending"
    return f"product_images/{sku_part}/{uuid.uuid4().hex}_{safe}"


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
    parent: models.ForeignKey = models.ForeignKey(  # type: ignore[misc]
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        help_text="Родительская категория (None для корня дерева).",
    )
    description: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Общее описание семейства (для страницы категории).",
    )
    instructions: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Общая инструкция по монтажу/управлению для семейства.",
    )
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
    description: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Описание линейки (общее для всех изданий Product).",
    )
    instructions: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Инструкция линейки (если отличается от категории).",
    )
    specs_text: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Характеристики линейки (до scoping по SKU).",
    )
    analogs_text: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Аналоги линейки (до scoping по SKU).",
    )
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
    description: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Описание конкретной модели/издания для карточки.",
    )
    specs_text: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Характеристики издания (напряжение/управление scoped).",
    )
    analogs_text: models.TextField = models.TextField(
        blank=True,
        default="",
        help_text="Аналоги для этого издания (артикула).",
    )
    is_published: models.BooleanField = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Видимость SKU в публичном каталоге.",
    )
    # Postgres FTS vector (auto-maintained by DB trigger; see migration).
    # Spec: ПЛАН §6 Iter 2 — SearchVector on name + sku_code + slug.
    search_vector = SearchVectorField(null=True, blank=True, editable=False)
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
        return f"{self.sku.sku_code} / {self.attribute.name} = {self.value}"  # type: ignore[attr-defined]


class ProductFile(models.Model):
    """Downloadable PDF (datasheet / certificate) attached to a SKU.

    Download center на PDP (docs/market-analysis.md B3). Публичное чтение;
    загрузка — staff/ETL. Валидация PDF: MIME + extension + magic + size
    (catalog.validators). upload_to с UUID — storage вне URL-угадывания.

    Args (fields):
        sku: FK SKU (CASCADE — удаление SKU удаляет файлы).
        title: человекочитаемое имя для UI, напр. «Паспорт HVA-5NM».
        file: FileField (PDF only; validators на поле).
        file_type: datasheet | certificate | catalog | other.
        is_published: видимость в публичном API (default True).
        sort_order: порядок в блоке «Документы» (меньше = выше).
        created_at / updated_at: авто-таймстампы.
    """

    class FileType(models.TextChoices):
        DATASHEET = "datasheet", "Паспорт / datasheet"
        CERTIFICATE = "certificate", "Сертификат"
        CATALOG = "catalog", "Каталог"
        OTHER = "other", "Прочее"

    sku: models.ForeignKey = models.ForeignKey(
        SKU,
        on_delete=models.CASCADE,
        related_name="files",
        help_text="SKU, к которому привязан документ.",
    )
    title: models.CharField = models.CharField(max_length=300)
    file: models.FileField = models.FileField(
        upload_to=product_file_upload_to,
        validators=[validate_pdf_upload],
        help_text="Только PDF; лимит и magic bytes — catalog.validators.",
    )
    file_type: models.CharField = models.CharField(
        max_length=20,
        choices=FileType.choices,
        default=FileType.DATASHEET,
        db_index=True,
    )
    is_published: models.BooleanField = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Видимость файла в публичном каталоге / PDP.",
    )
    sort_order: models.PositiveIntegerField = models.PositiveIntegerField(
        default=0,
        help_text="Порядок в блоке «Документы» (меньше = выше).",
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "файл продукта"
        verbose_name_plural = "файлы продуктов"
        ordering = ("sort_order", "title")

    def __str__(self) -> str:
        """Return 'title (sku_code)' for Admin readability."""
        return f"{self.title} ({self.sku.sku_code})"  # type: ignore[attr-defined]

    def clean(self) -> None:
        """Run PDF validators when file is present (Admin / full_clean)."""
        super().clean()
        if self.file:
            # FileField validators run on forms; clean() covers model.full_clean.
            name = Path(getattr(self.file, "name", "") or "").name
            if name:
                sanitize_upload_filename(name)
            validate_pdf_upload(self.file)


class ProductImage(models.Model):
    """Product photo for catalog card / PDP gallery (WebP).

    Spec: docs/data-quality-etl.md §2 — изображения из Tilda Store CSV.
    `source_url` — идемпотентность ETL (не качать повторно).

    Args (fields):
        sku: FK SKU (CASCADE).
        image: ImageField (WebP/JPEG/PNG на входе; ETL пишет WebP).
        alt: alt-текст для a11y / SEO.
        source_url: исходный URL Tilda CDN (unique per SKU).
        sort_order: 0 = primary (карточка каталога).
        is_published: видимость в публичном API.
    """

    sku: models.ForeignKey = models.ForeignKey(
        SKU,
        on_delete=models.CASCADE,
        related_name="images",
        help_text="SKU, к которому привязано фото.",
    )
    image: models.ImageField = models.ImageField(
        upload_to=product_image_upload_to,
        validators=[validate_image_upload],
        help_text="WebP предпочтительно; JPEG/PNG допустимы.",
    )
    alt: models.CharField = models.CharField(max_length=300, blank=True, default="")
    source_url: models.URLField = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="Исходный URL (Tilda CDN) для идемпотентного ETL.",
    )
    sort_order: models.PositiveIntegerField = models.PositiveIntegerField(default=0)
    is_published: models.BooleanField = models.BooleanField(default=True, db_index=True)
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "изображение продукта"
        verbose_name_plural = "изображения продуктов"
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("sku", "source_url"),
                name="catalog_productimage_sku_source_url_uniq",
                condition=~models.Q(source_url=""),
            ),
        ]

    def __str__(self) -> str:
        """Return alt or filename for Admin."""
        label = self.alt or Path(getattr(self.image, "name", "") or "").name or "image"
        return f"{label} ({self.sku.sku_code})"  # type: ignore[attr-defined]

    def clean(self) -> None:
        """Validate image when present."""
        super().clean()
        if self.image:
            name = Path(getattr(self.image, "name", "") or "").name
            if name:
                sanitize_upload_filename(name)
            validate_image_upload(self.image)
