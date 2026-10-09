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

# Product/SKU text fields an ETL series enricher may rewrite from manuals.
ETL_COPY_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "instructions",
    "specs_text",
    "analogs_text",
)
COPY_LOCKED_HELP = (
    "Название и тексты правили в админке: обогащение серии из мануала их не "
    "перезаписывает. Ставится само при сохранении правок; снимите галочку, "
    "чтобы вернуть канон."
)
# Set on an instance by Admin save paths; any other save keeps locked fields.
ADMIN_EDIT_FLAG = "_admin_edit"


def _keep_locked_fields(
    instance: models.Model,
    *,
    locked: bool,
    fields: tuple[str, ...],
    update_fields: object,
) -> None:
    """Restore DB values of ``fields`` unless the save comes from Admin.

    ETL, management commands and Celery jobs may assign copy/values freely;
    while the row is locked their writes become no-ops.
    """
    if instance.pk is None or not locked or instance.__dict__.pop(ADMIN_EDIT_FLAG, False):
        return
    own = {f.name for f in instance._meta.concrete_fields}
    wanted = [
        f
        for f in fields
        if f in own and (update_fields is None or f in update_fields)  # type: ignore[operator]
    ]
    if not wanted:
        return
    stored = type(instance)._default_manager.filter(pk=instance.pk).values(*wanted).first()
    for field, value in (stored or {}).items():
        setattr(instance, field, value)


def product_file_upload_to(instance: ProductFile, filename: str) -> str:
    """Store under product_files/<sku_id>/<uuid>_<safe_basename>.

    UUID в имени — не угадывать URL; basename проходит sanitize.
    """
    safe = sanitize_upload_filename(filename)
    sku_part = instance.sku_id if instance.sku_id is not None else "pending"
    return f"product_files/{sku_part}/{uuid.uuid4().hex}_{safe}"


def product_image_upload_to(instance: ProductImage, filename: str) -> str:
    """Store under product_images/<sku_id>/<uuid>_<safe_basename>.webp."""
    from catalog.etl.webp import webp_upload_basename

    safe = webp_upload_basename(sanitize_upload_filename(filename))
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

    name: models.CharField = models.CharField("название", max_length=200)
    slug: models.SlugField = models.SlugField(
        "сегмент URL",
        max_length=200,
        unique=True,
        db_index=True,
    )
    parent: models.ForeignKey = models.ForeignKey(  # type: ignore[misc]
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="родитель",
        help_text="Родительская категория (пусто = корень дерева).",
    )
    description: models.TextField = models.TextField(
        "описание",
        blank=True,
        default="",
        help_text="Общее описание линейки продукции (для страницы категории).",
    )
    instructions: models.TextField = models.TextField(
        "инструкция",
        blank=True,
        default="",
        help_text="Общая инструкция по монтажу/управлению для линейки продукции.",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

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
        verbose_name="категория",
        help_text="Категория товара (обязательная). Удалить категорию с товарами нельзя.",
    )
    name: models.CharField = models.CharField("название", max_length=200)
    slug: models.SlugField = models.SlugField(
        "сегмент URL",
        max_length=200,
        unique=True,
        db_index=True,
    )
    description: models.TextField = models.TextField(
        "описание",
        blank=True,
        default="",
        help_text="Описание линейки (общее для всех изданий продукта).",
    )
    instructions: models.TextField = models.TextField(
        "инструкция",
        blank=True,
        default="",
        help_text="Инструкция линейки (если отличается от категории).",
    )
    specs_text: models.TextField = models.TextField(
        "характеристики",
        blank=True,
        default="",
        help_text="Характеристики линейки (до уточнения по артикулу SKU).",
    )
    analogs_text: models.TextField = models.TextField(
        "аналоги",
        blank=True,
        default="",
        help_text="Аналоги линейки (до уточнения по артикулу SKU).",
    )
    copy_locked: models.BooleanField = models.BooleanField(
        "тексты правлены вручную",
        default=False,
        help_text=COPY_LOCKED_HELP,
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "продукт"
        verbose_name_plural = "продукты"
        ordering = ("name",)

    def __str__(self) -> str:
        """Return the product name for Admin and logs."""
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        """Keep Admin-locked copy (see ``copy_locked``)."""
        _keep_locked_fields(
            self,
            locked=self.copy_locked,
            fields=ETL_COPY_FIELDS,
            update_fields=kwargs.get("update_fields"),
        )
        super().save(*args, **kwargs)  # type: ignore[arg-type]


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
        stock_qty: остаток со склада (выгрузка 1С); витрина видит только in_stock.
        stock_qty_ma: остаток исполнений 4–20 мА (спецзаказ) из той же выгрузки.
        stock_updated_at: когда последний раз обновили остаток из выгрузки.
        description: опц. описание для карточки.
        is_published: видимость в каталоге (default True).
        created_at / updated_at: авто-таймстампы.
    """

    product: models.ForeignKey = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="skus",
        verbose_name="продукт",
        help_text="Продукт/линейка (обязательный). Удалить линейку с артикулами нельзя.",
    )
    name: models.CharField = models.CharField("название", max_length=300)
    slug: models.SlugField = models.SlugField(
        "сегмент URL",
        max_length=300,
        unique=True,
        db_index=True,
    )
    sku_code: models.CharField = models.CharField(
        "артикул",
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Артикул (уникален, не пуст), напр. HVA-5NM или BV215.",
    )
    analog_belimo_code: models.CharField | None = models.CharField(
        "код аналога Belimo",
        max_length=100,
        null=True,
        blank=True,
        default=None,
        help_text="Код аналога Belimo (для будущей карты аналогов).",
    )
    price: models.DecimalField | None = models.DecimalField(
        "цена",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=("Цена для КП менеджеру. В публичный API не попадает (см. настройку «показывать цены на сайте»)."),
    )
    stock_qty: models.IntegerField = models.IntegerField(
        "остаток",
        default=0,
        help_text="Количество на складе (из выгрузки 1С). На сайте только «есть / нет».",
    )
    stock_qty_ma: models.IntegerField = models.IntegerField(
        "остаток 4–20 мА",
        default=0,
        help_text=(
            "Свободный остаток исполнений 4–20 мА (спецзаказ). В выгрузке 1С "
            "это отдельная строка того же артикула с пометкой 4–20 мА. "
            "На сайте только «есть / нет»."
        ),
    )
    stock_updated_at: models.DateTimeField | None = models.DateTimeField(
        "остаток обновлён",
        null=True,
        blank=True,
        default=None,
        help_text="Время последней загрузки остатков из выгрузки 1С.",
    )
    first_published_at: models.DateTimeField | None = models.DateTimeField(
        "впервые на сайте",
        null=True,
        blank=True,
        default=None,
        db_index=True,
        help_text=(
            "Когда SKU впервые стал виден в публичном каталоге. "
            "Окно «Новое» — 30 суток; не путать с датами создания/обновления ETL."
        ),
    )
    description: models.TextField = models.TextField(
        "описание",
        blank=True,
        default="",
        help_text="Описание конкретной модели/издания для карточки.",
    )
    specs_text: models.TextField = models.TextField(
        "характеристики",
        blank=True,
        default="",
        help_text="Характеристики издания (напряжение и управление — по артикулу).",
    )
    analogs_text: models.TextField = models.TextField(
        "аналоги",
        blank=True,
        default="",
        help_text="Аналоги для этого издания (артикула).",
    )
    copy_locked: models.BooleanField = models.BooleanField(
        "тексты правлены вручную",
        default=False,
        help_text=COPY_LOCKED_HELP,
    )
    is_published: models.BooleanField = models.BooleanField(
        "опубликован",
        default=True,
        db_index=True,
        help_text="Видимость SKU в публичном каталоге.",
    )
    # Postgres FTS vector (auto-maintained by DB trigger; see migration).
    # Spec: ПЛАН §6 Iter 2 — SearchVector on name + sku_code + slug.
    search_vector = SearchVectorField(
        "поисковый вектор",
        null=True,
        blank=True,
        editable=False,
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "артикул (SKU)"
        verbose_name_plural = "артикулы (SKU)"
        ordering = ("sku_code",)

    def __str__(self) -> str:
        """Return the SKU name for Admin and logs."""
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        """Stamp ``first_published_at``; keep Admin-locked copy."""
        from catalog.newness import ensure_first_published_at

        ensure_first_published_at(self)
        _keep_locked_fields(
            self,
            locked=self.copy_locked,
            fields=ETL_COPY_FIELDS,
            update_fields=kwargs.get("update_fields"),
        )
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    @property
    def in_stock(self) -> bool:
        """True when warehouse quantity is positive (public availability label)."""
        return int(self.stock_qty or 0) > 0

    @property
    def in_stock_ma(self) -> bool:
        """True when 4–20 mA (special-order) units are on hand."""
        return int(self.stock_qty_ma or 0) > 0


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

    name: models.CharField = models.CharField("название", max_length=200)
    slug: models.SlugField = models.SlugField(
        "ключ фильтра",
        max_length=100,
        unique=True,
        db_index=True,
    )
    unit: models.CharField = models.CharField(
        "единица",
        max_length=50,
        blank=True,
        default="",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

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
        verbose_name="артикул (SKU)",
    )
    attribute: models.ForeignKey = models.ForeignKey(
        Attribute,
        on_delete=models.PROTECT,
        related_name="values",
        verbose_name="атрибут",
    )
    value: models.CharField = models.CharField("значение", max_length=200)
    is_manual: models.BooleanField = models.BooleanField(
        "правлено вручную",
        default=False,
        help_text=(
            "Значение задано в админке: обогащение серии из мануала его не "
            "удаляет и не перезаписывает. Снимите галочку, чтобы вернуть канон."
        ),
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "значение атрибута"
        verbose_name_plural = "значения атрибутов"
        unique_together = (("sku", "attribute"),)
        ordering = ("attribute__name",)

    def __str__(self) -> str:
        """Return 'sku_code / attribute_name = value' for Admin readability."""
        return f"{self.sku.sku_code} / {self.attribute.name} = {self.value}"  # type: ignore[attr-defined]

    def save(self, *args: object, **kwargs: object) -> None:
        """Keep an Admin-edited value (see ``is_manual``)."""
        _keep_locked_fields(
            self,
            locked=self.is_manual,
            fields=("value",),
            update_fields=kwargs.get("update_fields"),
        )
        super().save(*args, **kwargs)  # type: ignore[arg-type]


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
        DATASHEET = "datasheet", "Паспорт"
        CERTIFICATE = "certificate", "Сертификат"
        CATALOG = "catalog", "Каталог"
        OTHER = "other", "Прочее"

    sku: models.ForeignKey = models.ForeignKey(
        SKU,
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="артикул (SKU)",
        help_text="Артикул (SKU), к которому привязан документ.",
    )
    title: models.CharField = models.CharField("название", max_length=300)
    file: models.FileField = models.FileField(
        "файл",
        upload_to=product_file_upload_to,
        validators=[validate_pdf_upload],
        help_text="Только PDF; размер и тип файла проверяются при загрузке.",
    )
    file_type: models.CharField = models.CharField(
        "тип файла",
        max_length=20,
        choices=FileType.choices,
        default=FileType.DATASHEET,
        db_index=True,
    )
    is_published: models.BooleanField = models.BooleanField(
        "опубликован",
        default=True,
        db_index=True,
        help_text="Видимость файла в публичном каталоге и на карточке товара.",
    )
    sort_order: models.PositiveIntegerField = models.PositiveIntegerField(
        "порядок",
        default=0,
        help_text="Порядок в блоке «Документы» (меньше = выше).",
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

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
        image_card: лёгкий WebP для list/mobile (≤720px); полный кадр в ``image``.
    """

    sku: models.ForeignKey = models.ForeignKey(
        SKU,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name="артикул (SKU)",
        help_text="Артикул (SKU), к которому привязано фото.",
    )
    image: models.ImageField = models.ImageField(
        "изображение",
        upload_to=product_image_upload_to,
        validators=[validate_image_upload],
        help_text="WebP предпочтительно; JPEG/PNG допустимы. Полный кадр для страницы артикула.",
    )
    image_card: models.ImageField = models.ImageField(
        "превью карточки",
        upload_to=product_image_upload_to,
        blank=True,
        default="",
        validators=[validate_image_upload],
        help_text="Лёгкий WebP для каталога/мобилок (генерируется из полного кадра).",
    )
    alt: models.CharField = models.CharField(
        "альтернативный текст",
        max_length=300,
        blank=True,
        default="",
    )
    source_url: models.URLField = models.URLField(
        "исходный URL",
        max_length=500,
        blank=True,
        default="",
        help_text="Исходный URL (CDN Tilda) для повторного импорта без дублей.",
    )
    sort_order: models.PositiveIntegerField = models.PositiveIntegerField(
        "порядок",
        default=0,
    )
    is_published: models.BooleanField = models.BooleanField(
        "опубликовано",
        default=True,
        db_index=True,
    )
    hidden_by_editor: models.BooleanField = models.BooleanField(
        "скрыто вручную",
        default=False,
        help_text=(
            "Фото сняли с публикации в админке: аудит галереи и загрузка "
            "медиа его не возвращают. Снимается, если снова включить «опубликовано»."
        ),
    )
    created_at: models.DateTimeField = models.DateTimeField("создано", auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField("обновлено", auto_now=True)

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

    def save(self, *args: object, **kwargs: object) -> None:
        """Persist row; re-encode JPEG/PNG uploads to WebP; sync card preview.

        A photo hidden in Admin (``hidden_by_editor``) stays unpublished
        whatever ETL/media job saves it.
        """
        from catalog.etl.webp import attach_image_card, ensure_field_file_webp

        _keep_locked_fields(
            self,
            locked=self.hidden_by_editor,
            fields=("is_published",),
            update_fields=kwargs.get("update_fields"),
        )
        raw_fields = kwargs.get("update_fields")
        update_fields: frozenset[str] | None = None
        if isinstance(raw_fields, (list, tuple, set, frozenset)):
            update_fields = frozenset(str(name) for name in raw_fields)

        only_card = update_fields is not None and update_fields <= {
            "image_card",
            "updated_at",
        }
        if only_card:
            super().save(*args, **kwargs)  # type: ignore[arg-type]
            return

        sync_card = update_fields is None or "image" in update_fields
        if self.image:
            ensure_field_file_webp(self.image)
            if sync_card:
                attach_image_card(self)
                if update_fields is not None and "image_card" not in update_fields:
                    kwargs["update_fields"] = [*update_fields, "image_card"]
        elif sync_card and self.image_card:
            self.image_card.delete(save=False)
            self.image_card = ""
            if update_fields is not None and "image_card" not in update_fields:
                kwargs["update_fields"] = [*update_fields, "image_card"]

        super().save(*args, **kwargs)  # type: ignore[arg-type]


class AnalogMap(models.Model):
    """Карта аналогов: сторонний бренд + артикул → Hoocon SKU (ЛК-10).

    Редактируется в Admin (роль «Инженер ОВК» — по групповой матрице);
    публичный подбор идёт через ``analogs_find`` в catalog.services.
    ``foreign_code`` нормализуется (upper, без пробелов/дефисов), чтобы
    матчить написания вида «NM24A-SR» / «nm24a sr».
    """

    brand = models.CharField(
        "сторонний бренд",
        max_length=100,
        db_index=True,
        help_text="Напр. Belimo, Siemens, Danfoss.",
    )
    foreign_code = models.CharField(
        "артикул аналога",
        max_length=100,
        help_text="Как у производителя-аналога (регистр не важен).",
    )
    foreign_code_key = models.CharField(
        "ключ артикула",
        max_length=100,
        editable=False,
        db_index=True,
        help_text="Нормализованный ключ совпадения (верхний регистр, без пробелов/дефисов).",
    )
    sku = models.ForeignKey(
        "SKU",
        on_delete=models.CASCADE,
        related_name="analog_maps",
        verbose_name="наш артикул (SKU)",
    )
    torque_nm = models.PositiveSmallIntegerField(
        "момент, Нм",
        null=True,
        blank=True,
    )
    voltage = models.CharField("питание", max_length=30, blank=True, default="")
    control = models.CharField(
        "управление",
        max_length=50,
        blank=True,
        default="",
        help_text="Напр. 3-точечное, 0-10В, 4-20мА.",
    )
    spring_return = models.BooleanField(
        "пружинный возврат",
        default=False,
    )
    note = models.CharField("примечание", max_length=300, blank=True, default="")
    is_active = models.BooleanField("активна", default=True, db_index=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "аналог стороннего артикула"
        verbose_name_plural = "карта аналогов"
        ordering = ("brand", "foreign_code")
        constraints = [
            models.UniqueConstraint(
                fields=("brand", "foreign_code_key"),
                name="catalog_analogmap_brand_code_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.brand} {self.foreign_code} → {self.sku_id}"

    def save(self, *args: object, **kwargs: object) -> None:
        """Normalize foreign_code_key from brand + foreign_code."""
        self.foreign_code_key = normalize_analog_code(self.foreign_code)
        super().save(*args, **kwargs)  # type: ignore[arg-type]


def normalize_analog_code(raw: str) -> str:
    """Normalize a foreign article code for matching (upper, alnum only)."""
    return "".join(ch for ch in (raw or "").upper() if ch.isalnum())
