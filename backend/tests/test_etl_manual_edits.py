"""ETL vs Admin edits: series enrichment must not wipe what editors changed.

Regression for H16 (attributes/texts wiped, no transaction), H17 (label
depends on last ETL), H18 (gallery audit republished editor-hidden photos).
"""

from __future__ import annotations

from importlib import import_module

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from catalog.etl.attr_registry import CANONICAL_ATTRS
from catalog.etl.attr_write import attribute_cache, ensure_attribute, set_sku_attribute
from catalog.etl.series_copy_dafu import SERIES_DESCRIPTION, apply_dafu_enrichment
from catalog.models import SKU, Attribute, AttributeValue, Category, Product, ProductImage


def _dafu_sku() -> SKU:
    cat, _ = Category.objects.get_or_create(
        slug="elektroprivody-s-pruzhinnym-vozvratom",
        defaults={"name": "Пружина"},
    )
    product = Product.objects.create(
        slug="privod-vozdushniy-pruzhina-dafu-5nm-manual",
        name="DA5FU",
        category=cat,
    )
    return SKU.objects.create(
        product=product,
        sku_code="DA5FU24-D",
        name="DA5FU24-D",
        slug="da5fu24-d-manual",
        is_published=True,
    )


def _values(sku: SKU) -> dict[str, AttributeValue]:
    return {av.attribute.slug: av for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")}


def _png() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (1200, 1500), color=(20, 80, 140)).save(buf, format="PNG")
    return buf.getvalue()


def _staff_client(client, django_user_model):  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_user(
        username="catalog-editor",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_enrichment_keeps_admin_edited_attribute_and_drops_stale_etl_rows() -> None:
    """Symptom: every enrich run deleted all AttributeValue, Admin edits too."""
    sku = _dafu_sku()
    set_sku_attribute(sku, slug="weight", value="1,4 кг", name="Масса")
    AttributeValue.objects.filter(sku=sku, attribute__slug="weight").update(is_manual=True)
    set_sku_attribute(sku, slug="legacy-junk", value="мусор Tilda", name="Старое поле")

    apply_dafu_enrichment()

    rows = _values(sku)
    assert rows["weight"].value == "1,4 кг"
    assert rows["weight"].is_manual is True
    assert "legacy-junk" not in rows
    assert rows["running-time"].value == "< 70 с / возврат пружины < 20 с"


@pytest.mark.django_db
def test_enrichment_keeps_locked_copy_but_rewrites_unlocked() -> None:
    sku = _dafu_sku()
    product = sku.product
    Product.objects.filter(pk=product.pk).update(description="Текст менеджера", copy_locked=True)
    SKU.objects.filter(pk=sku.pk).update(description="Своё описание", name="Своё имя", copy_locked=True)

    apply_dafu_enrichment()

    product.refresh_from_db()
    sku.refresh_from_db()
    assert product.description == "Текст менеджера"
    assert sku.description == "Своё описание"
    assert sku.name == "Своё имя"

    Product.objects.filter(pk=product.pk).update(copy_locked=False)
    apply_dafu_enrichment()
    product.refresh_from_db()
    assert product.description == SERIES_DESCRIPTION


@pytest.mark.django_db
def test_locked_copy_survives_any_non_admin_save() -> None:
    """Root: the lock lives on the model, so legacy writers cannot bypass it."""
    sku = _dafu_sku()
    SKU.objects.filter(pk=sku.pk).update(description="Правка", copy_locked=True)
    sku.refresh_from_db()

    sku.description = "ETL"
    sku.save(update_fields=["description"])
    sku.refresh_from_db()
    assert sku.description == "Правка"

    sku.description = "ETL full save"
    sku.save()
    sku.refresh_from_db()
    assert sku.description == "Правка"

    from catalog.models import ADMIN_EDIT_FLAG

    sku.description = "Новая правка из админки"
    sku.__dict__[ADMIN_EDIT_FLAG] = True
    sku.save(update_fields=["description"])
    sku.refresh_from_db()
    assert sku.description == "Новая правка из админки"


@pytest.mark.django_db
def test_manual_attribute_value_survives_direct_save() -> None:
    sku = _dafu_sku()
    attr = ensure_attribute("weight", "Масса", "кг")
    row = AttributeValue.objects.create(sku=sku, attribute=attr, value="1,4 кг", is_manual=True)
    row.value = "< 1,5 кг"
    row.save(update_fields=["value"])
    row.refresh_from_db()
    assert row.value == "1,4 кг"
    assert set_sku_attribute(sku, slug="weight", value="< 1,5 кг", name="Масса") is False


@pytest.mark.django_db
def test_enrichment_failure_rolls_back_whole_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Symptom: a crash mid-run left the SKU with no attributes at all."""
    sku = _dafu_sku()
    set_sku_attribute(sku, slug="moment", value="5 Нм", name="Крутящий момент")
    import catalog.etl.series_copy_dafu as dafu

    calls = {"n": 0}
    real = dafu.set_sku_attribute

    def flaky(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] > 3:
            raise RuntimeError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(dafu, "set_sku_attribute", flaky)
    with pytest.raises(RuntimeError):
        apply_dafu_enrichment()

    rows = _values(sku)
    assert rows["moment"].value == "5 Нм"
    assert set(rows) == {"moment"}


@pytest.mark.django_db
def test_attribute_label_does_not_depend_on_last_etl() -> None:
    """H17 symptom: HVA wrote «Степень защиты», DAFU «… корпуса» — label flipped."""
    ensure_attribute("ip-rating", "Степень защиты")
    ensure_attribute("ip-rating", "Степень защиты корпуса")
    ensure_attribute("ip-rating", "Степень защиты")
    attr = Attribute.objects.get(slug="ip-rating")
    assert (attr.name, attr.unit) == CANONICAL_ATTRS["ip-rating"]

    ensure_attribute("transformer-va", "Мощность трансформатора", "ВА")
    assert Attribute.objects.get(slug="transformer-va").unit == "В·А"


@pytest.mark.django_db
def test_unregistered_attribute_keeps_admin_rename() -> None:
    attr = ensure_attribute("custom-note", "Заметка")
    Attribute.objects.filter(pk=attr.pk).update(name="Заметка менеджера")
    ensure_attribute("custom-note", "Заметка")
    assert Attribute.objects.get(pk=attr.pk).name == "Заметка менеджера"


_SERIES_MODULES = (
    "series_copy_dafu",
    "series_copy_damu",
    "series_copy_damqu",
    "series_copy_safu",
    "series_copy_samu",
    "series_copy_hvdf",
    "series_copy_hva",
    "series_copy_hvd_air",
    "series_copy_hv_extra",
)


@pytest.mark.parametrize("module_name", _SERIES_MODULES)
def test_series_shared_attrs_are_registered(module_name: str) -> None:
    """Root: every shared slug an enricher writes has one canonical label."""
    module = import_module(f"catalog.etl.{module_name}")
    rows = [
        row
        for name in dir(module)
        if name.startswith(("SHARED", "_SHARED"))
        for row in getattr(module, name)
        if isinstance(row, tuple) and len(row) >= 4
    ]
    assert rows, module_name
    missing = sorted({row[1] for row in rows} - CANONICAL_ATTRS.keys())
    assert not missing, (module_name, missing)


@pytest.mark.django_db
def test_editor_hidden_photo_stays_hidden_after_audit_and_media_save() -> None:
    """H18 symptom: prune/media re-attach republished a photo hidden by hand."""
    from catalog.etl.product_image_audit import prune_inferior_hero_duplicates, restore_secondary_gallery_angles

    sku = _dafu_sku()
    hidden = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("hero.png", _png(), content_type="image/png"),
        alt="DA5FU | фото 2",
        source_url="https://hoocon.ru/.local-assets/da/da5fu-product.webp",
        sort_order=0,
        is_published=False,
        hidden_by_editor=True,
    )

    prune_inferior_hero_duplicates(dry_run=False)
    restore_secondary_gallery_angles(dry_run=False)
    hidden.refresh_from_db()
    assert hidden.is_published is False

    hidden.is_published = True
    hidden.save(update_fields=["is_published", "updated_at"])
    hidden.refresh_from_db()
    assert hidden.is_published is False


@pytest.mark.django_db
def test_admin_edit_sets_copy_lock(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Loaded surface: the Product change form marks texts as manual."""
    sku = _dafu_sku()
    product = sku.product
    staff = _staff_client(client, django_user_model)
    url = reverse("admin:catalog_product_change", args=[product.pk])
    response = staff.post(
        url,
        {
            "name": product.name,
            "slug": product.slug,
            "category": product.category_id,
            "description": "Описание от менеджера",
            "instructions": "",
            "specs_text": "",
            "analogs_text": "",
            "_save": "Сохранить",
        },
    )
    assert response.status_code == 302, response.content[:500]
    product.refresh_from_db()
    assert product.copy_locked is True
    assert product.description == "Описание от менеджера"

    apply_dafu_enrichment()
    product.refresh_from_db()
    assert product.description == "Описание от менеджера"


@pytest.mark.django_db
def test_admin_attribute_edit_marks_manual(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    sku = _dafu_sku()
    attr = ensure_attribute("weight", "Масса", "кг")
    row = AttributeValue.objects.create(sku=sku, attribute=attr, value="< 1,5 кг")
    staff = _staff_client(client, django_user_model)
    url = reverse("admin:catalog_attributevalue_change", args=[row.pk])
    response = staff.post(
        url,
        {"sku": sku.pk, "attribute": attr.pk, "value": "1,45 кг", "_save": "Сохранить"},
    )
    assert response.status_code == 302, response.content[:500]
    row.refresh_from_db()
    assert row.value == "1,45 кг"
    assert row.is_manual is True


@pytest.mark.django_db
def test_attribute_lookup_is_cached_within_enrichment_run(django_assert_max_num_queries) -> None:
    """N+1: каждый set_sku_attribute заново делал get_or_create Attribute на каждый SKU."""
    category = Category.objects.create(name="Cache", slug="attr-cache")
    product = Product.objects.create(name="Cache", slug="attr-cache-p", category=category)
    skus = [
        SKU.objects.create(product=product, name=f"S{i}", slug=f"attr-cache-{i}", sku_code=f"AC-{i}") for i in range(5)
    ]
    with attribute_cache():
        set_sku_attribute(skus[0], slug="torque", value="5", name="Момент", unit="Н·м")
        # Остальные SKU: только поиск строки + insert, без запроса Attribute.
        with django_assert_max_num_queries(2 * (len(skus) - 1)):
            for sku in skus[1:]:
                set_sku_attribute(sku, slug="torque", value="5", name="Момент", unit="Н·м")
    assert AttributeValue.objects.filter(attribute__slug="torque").count() == len(skus)


def test_enrichers_run_inside_attribute_cache() -> None:
    """Кэш включается на входе каждого обогатителя серии, снаружи транзакции."""
    import inspect

    from catalog.etl import series_copy_damu, series_copy_hva, specs_to_attrs

    for func in (
        series_copy_damu.apply_damu_enrichment,
        series_copy_hva.apply_hva_enrichment,
        specs_to_attrs.enrich_catalog_cards,
    ):
        source = inspect.getsource(inspect.getmodule(func))
        assert f"@cached_attributes\n@transaction.atomic\ndef {func.__name__}(" in source or (
            f"@cached_attributes\ndef {func.__name__}(" in source
        )
