"""Tests for SEO legacy redirect rebuild (Tilda inventory → live nested paths)."""

from __future__ import annotations

import pytest

from catalog.etl.seo_legacy_redirects import (
    ensure_article_tpost_redirects,
    ensure_seo_legacy_redirects,
    preferred_sku_for_product,
    resolve_legacy_slug_to_sku,
)
from catalog.models import SKU, Category, Product
from content.article_slug_renames import ARTICLE_SLUG_RENAMES, apply_article_slug_renames
from content.models import Article, News
from content.news_slug_renames import NEWS_SLUG_RENAMES, apply_news_slug_renames
from redirects.models import Redirect


@pytest.fixture
def air_category(db: None) -> Category:
    return Category.objects.create(
        name="Воздушные",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )


@pytest.fixture
def hvd_product(air_category: Category) -> Product:
    return Product.objects.create(
        name="HVD-5",
        slug="privod-vozdushniy-hvd-5nm",
        category=air_category,
    )


@pytest.mark.django_db
def test_preferred_sku_prefers_230s(hvd_product: Product) -> None:
    SKU.objects.create(
        product=hvd_product,
        sku_code="HVD24-5",
        slug="privod-vozdushniy-hvd-5nm-hvd24-5",
        name="24",
        is_published=True,
    )
    preferred = SKU.objects.create(
        product=hvd_product,
        sku_code="HVD230S-5",
        slug="privod-vozdushniy-hvd-5nm-hvd230s-5",
        name="230S",
        is_published=True,
    )
    assert preferred_sku_for_product(hvd_product) == preferred


@pytest.mark.django_db
def test_ensure_redirects_family_and_edition(hvd_product: Product) -> None:
    sku = SKU.objects.create(
        product=hvd_product,
        sku_code="HVD230S-5",
        slug="privod-vozdushniy-hvd-5nm-hvd230s-5",
        name="230S",
        is_published=True,
    )
    Redirect.objects.create(
        from_path="/privod-vozdushniy-hvd-5nm",
        to_path="/catalog/elektroprivod-vozdushniy-bez-vozvratnoy-pruzhiny/privod-vozdushniy-hvd-5nm",
        status_code=301,
        is_active=True,
    )

    summary = ensure_seo_legacy_redirects()

    assert summary.upserted >= 1
    family = Redirect.objects.get(from_path="/privod-vozdushniy-hvd-5nm")
    assert family.to_path.endswith(f"/{sku.slug}")
    assert "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata" in family.to_path
    edition = Redirect.objects.get(from_path=f"/{sku.slug}")
    assert edition.to_path == family.to_path
    dead_nested = Redirect.objects.get(
        from_path=("/catalog/elektroprivod-vozdushniy-bez-vozvratnoy-pruzhiny/privod-vozdushniy-hvd-5nm"),
    )
    assert dead_nested.to_path == family.to_path


@pytest.mark.django_db
def test_resolve_brass_legacy_slug(db: None) -> None:
    cat = Category.objects.create(name="Краны", slug="sharovye-krany")
    product = Product.objects.create(name="BV215", slug="8100-bv215", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-BV215A",
        slug="8100-bv215a",
        name="A",
        is_published=True,
    )
    assert resolve_legacy_slug_to_sku("sharovoy-kran-bv215") == sku


@pytest.mark.django_db
def test_article_tpost_redirects() -> None:
    old = "2zbgj89cp1-primenenie-privodov-v-sistemah-ventilyat"
    new = ARTICLE_SLUG_RENAMES[old]
    Article.objects.create(title="x", slug=new, body="<p>x</p>", is_published=True)

    n = ensure_article_tpost_redirects()

    assert n >= 1
    redir = Redirect.objects.get(from_path=f"/statyi/tpost/{old}")
    assert redir.to_path == f"/statyi/{new}"


@pytest.mark.django_db
def test_apply_article_renames_writes_tpost() -> None:
    old = "4uicugaoh1-spetsifikatsiya-modelnogo-ryada-privodov"
    new = ARTICLE_SLUG_RENAMES[old]
    Article.objects.create(title="x", slug=old, body="<p>x</p>", is_published=True)

    apply_article_slug_renames()

    assert Redirect.objects.get(from_path=f"/statyi/tpost/{old}").to_path == f"/statyi/{new}"


@pytest.mark.django_db
def test_news_underscore_rename() -> None:
    old = "mirklimata_2025"
    new = NEWS_SLUG_RENAMES[old]
    News.objects.create(title="Мир климата", slug=old, body="<p>x</p>", is_published=True)

    apply_news_slug_renames()

    assert not News.objects.filter(slug=old).exists()
    assert News.objects.filter(slug=new).exists()
    assert Redirect.objects.get(from_path=f"/novosti/{old}").to_path == f"/novosti/{new}"
    assert Redirect.objects.get(from_path=f"/news/{old}").to_path == f"/novosti/{new}"


@pytest.mark.django_db
def test_static_inventory_redirects(db: None) -> None:
    ensure_seo_legacy_redirects()
    assert Redirect.objects.get(from_path="/sale").to_path == "/catalog"
    assert Redirect.objects.get(from_path="/sitemap").to_path == "/sitemap.xml"
    assert Redirect.objects.get(
        from_path="/elektroprivody-dlya-zaslonok-ventilyatsii",
    ).to_path.endswith("elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata")
