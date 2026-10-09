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
    assert Redirect.objects.get(from_path="/news").to_path == "/novosti"
    assert Redirect.objects.get(
        from_path="/elektroprivody-dlya-zaslonok-ventilyatsii",
    ).to_path.endswith("elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata")


@pytest.mark.django_db
def test_resolve_tilda_edition_suffix(db: None) -> None:
    """Webmaster 404: flat /privod-…-24v-dst must resolve to the matching edition."""
    cat = Category.objects.create(
        name="Противопожарные",
        slug="elektroprivody-protivopozharnye-i-dymovye",
    )
    product = Product.objects.create(
        name="SA5",
        slug="privod-protivopozharniy-5nm",
        category=cat,
    )
    target = SKU.objects.create(
        product=product,
        sku_code="sa5fu24-dst",
        slug="privod-protivopozharniy-5nm-sa5fu24-dst",
        name="24 DST",
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        sku_code="sa5fu230-dst",
        slug="privod-protivopozharniy-5nm-sa5fu230-dst",
        name="230 DST",
        is_published=True,
    )

    resolved = resolve_legacy_slug_to_sku("privod-protivopozharniy-5nm-24v-dst")
    assert resolved == target


@pytest.mark.django_db
def test_resolve_sale_suffix_and_brass_dvuh(db: None) -> None:
    cat = Category.objects.create(name="Краны", slug="sharovye-krany")
    product = Product.objects.create(name="BV215", slug="8100-bv215", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-BV215A",
        slug="8100-bv215a",
        name="A",
        is_published=True,
    )
    assert resolve_legacy_slug_to_sku("sharovoy-dvuhhodoviy-kran-bv215-sale") == sku


@pytest.mark.django_db
def test_flat_tpost_redirects() -> None:
    old = "vvme9fxcy1-ognezaderzhivayuschii-klapan-printsip-ra"
    new = ARTICLE_SLUG_RENAMES[old]
    Article.objects.create(title="x", slug=new, body="<p>x</p>", is_published=True)

    ensure_article_tpost_redirects()

    assert Redirect.objects.get(from_path=f"/tpost/{old}").to_path == f"/statyi/{new}"


@pytest.mark.django_db
def test_etl_keeps_admin_edited_redirect(hvd_product: Product) -> None:
    """M47: ETL перезаписывал to_path, который поправили в админке."""
    SKU.objects.create(
        product=hvd_product,
        sku_code="HVD230S-5",
        slug="privod-vozdushniy-hvd-5nm-hvd230s-5",
        name="230S",
        is_published=True,
    )
    Redirect.objects.create(
        from_path="/privod-vozdushniy-hvd-5nm",
        to_path="/promo/hvd",
        status_code=302,
        edited_in_admin=True,
    )
    ensure_seo_legacy_redirects()
    row = Redirect.objects.get(from_path="/privod-vozdushniy-hvd-5nm")
    assert (row.to_path, row.status_code) == ("/promo/hvd", 302)


@pytest.mark.django_db
def test_etl_does_not_reenable_redirect_disabled_in_admin(hvd_product: Product) -> None:
    """M47: выключенный вручную редирект ETL включал обратно."""
    SKU.objects.create(
        product=hvd_product,
        sku_code="HVD230S-5",
        slug="privod-vozdushniy-hvd-5nm-hvd230s-5",
        name="230S",
        is_published=True,
    )
    Redirect.objects.create(
        from_path="/privod-vozdushniy-hvd-5nm",
        to_path="/catalog",
        is_active=False,
        edited_in_admin=True,
    )
    ensure_seo_legacy_redirects()
    assert Redirect.objects.get(from_path="/privod-vozdushniy-hvd-5nm").is_active is False


@pytest.mark.django_db
def test_collapse_redirect_chains_points_to_final_target() -> None:
    """M47: цепочки A → B → C схлопываются в один 301; ручные строки и циклы не трогаются."""
    from redirects.services import collapse_redirect_chains

    Redirect.objects.create(from_path="/a", to_path="/b")
    Redirect.objects.create(from_path="/b", to_path="/c")
    Redirect.objects.create(from_path="/c", to_path="/final")
    Redirect.objects.create(from_path="/manual", to_path="/b", edited_in_admin=True)
    Redirect.objects.create(from_path="/x", to_path="/y")
    Redirect.objects.create(from_path="/y", to_path="/x")

    assert collapse_redirect_chains(dry_run=True) == 2
    assert Redirect.objects.get(from_path="/a").to_path == "/b"

    assert collapse_redirect_chains() == 2
    assert Redirect.objects.get(from_path="/a").to_path == "/final"
    assert Redirect.objects.get(from_path="/b").to_path == "/final"
    assert Redirect.objects.get(from_path="/manual").to_path == "/b"
    assert Redirect.objects.get(from_path="/x").to_path == "/y"


@pytest.mark.django_db
def test_csv_seed_skips_admin_edited_rows(tmp_path) -> None:
    """M47 (sibling): CSV-сид редиректов тоже не перезаписывает ручные строки."""
    from redirects.services import load_redirects_from_csv

    Redirect.objects.create(from_path="/old", to_path="/manual-target", edited_in_admin=True)
    seed = tmp_path / "seed.csv"
    seed.write_text("from_path,to_path,status_code\n/old,/seed-target,301\n/new,/seed-target,301\n", encoding="utf-8")
    result = load_redirects_from_csv(seed)
    assert result["skipped"] == 1
    assert Redirect.objects.get(from_path="/old").to_path == "/manual-target"
    assert Redirect.objects.get(from_path="/new").to_path == "/seed-target"


@pytest.mark.django_db
def test_admin_save_marks_redirect_edited(admin_client) -> None:
    """M47: сохранение в админке ставит «правлено вручную»."""
    response = admin_client.post(
        "/admin/redirects/redirect/add/",
        {"from_path": "/promo-old", "to_path": "/promo-new", "status_code": 301, "is_active": "on"},
    )
    assert response.status_code == 302, response.content[:500]
    assert Redirect.objects.get(from_path="/promo-old").edited_in_admin is True
