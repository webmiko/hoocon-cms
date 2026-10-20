"""API tests for documentation hub list + family zip."""

from __future__ import annotations

import io
import zipfile

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse


def _seed_docs_family():
    """Two SKUs sharing one instruction + one passport each."""
    from catalog.models import SKU, Category, Product, ProductFile

    cat = Category.objects.create(name="DAMU hub", slug="damu-hub-api")
    product = Product.objects.create(
        name="DA2MU",
        slug="privod-vozdushniy-bez-pruzhini-damu-2nm-hub",
        category=cat,
    )
    sku_a = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-D",
        name="DA2MU24-D",
        slug="da2mu24-d-hub",
        is_published=True,
    )
    sku_b = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-DS",
        name="DA2MU24-DS",
        slug="da2mu24-ds-hub",
        is_published=True,
    )
    title = "Инструкция DA2MU (D/DS)"
    for sku, body in ((sku_a, b"%PDF-shared-a"), (sku_b, b"%PDF-shared-b")):
        pf = ProductFile(
            sku=sku,
            title=title,
            file_type=ProductFile.FileType.DATASHEET,
            is_published=True,
            sort_order=0,
        )
        pf.file.save(f"{sku.slug}-manual.pdf", ContentFile(body), save=True)
    for sku, body in (
        (sku_a, b"%PDF-pass-a"),
        (sku_b, b"%PDF-pass-b"),
    ):
        pf = ProductFile(
            sku=sku,
            title=f"Паспорт {sku.sku_code}",
            file_type=ProductFile.FileType.DATASHEET,
            is_published=True,
            sort_order=1,
        )
        pf.file.save(f"{sku.slug}-pass.pdf", ContentFile(body), save=True)
    return sku_a, sku_b


@pytest.mark.django_db
def test_docs_hub_list_dedupes_manuals(client) -> None:
    _seed_docs_family()
    response = client.get(reverse("catalog-docs"))
    assert response.status_code == 200
    data = response.json()
    titles = [f["title"] for f in data["files"]]
    assert titles.count("Инструкция DA2MU (D/DS)") == 1
    assert "Паспорт DA2MU24-D" in titles
    assert "Паспорт DA2MU24-DS" in titles
    families = {f["key"]: f for f in data["families"]}
    assert families["DA2MU"]["file_count"] == 3
    assert families["DA2MU"]["series"] == "DA"
    assert families["DA2MU"]["zip_path"].endswith("/DA2MU/zip/")


@pytest.mark.django_db
def test_docs_hub_list_filters(client) -> None:
    _seed_docs_family()
    by_kind = client.get(reverse("catalog-docs"), {"kind": "passport"})
    assert by_kind.status_code == 200
    assert all(f["kind"] == "passport" for f in by_kind.json()["files"])
    assert len(by_kind.json()["files"]) == 2

    by_q = client.get(reverse("catalog-docs"), {"q": "DA2MU24-DS"})
    assert by_q.status_code == 200
    titles = [f["title"] for f in by_q.json()["files"]]
    assert "Паспорт DA2MU24-DS" in titles

    by_series = client.get(reverse("catalog-docs"), {"series": "SA"})
    assert by_series.status_code == 200
    assert by_series.json()["files"] == []


@pytest.mark.django_db
def test_docs_family_zip_unique_and_etag(client) -> None:
    _seed_docs_family()
    url = reverse("catalog-docs-family-zip", kwargs={"key": "DA2MU"})
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert "DA2MU-docs.zip" in response["Content-Disposition"]
    etag = response["ETag"].strip('"')
    assert etag

    body = b"".join(response.streaming_content)
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = zf.namelist()
    assert len(names) == 3

    cached = client.get(url, HTTP_IF_NONE_MATCH=f'"{etag}"')
    assert cached.status_code == 304


@pytest.mark.django_db
def test_docs_family_zip_allows_the_measured_h81_size(client, monkeypatch) -> None:
    """H8101 и H8102 весят 254 и 247 МБ. Такая сумма не должна отвечать 413."""
    import tempfile

    from catalog.docs_hub import FAMILY_ZIP_MAX_BYTES

    # Аудит 2026-10: сумма файлов семейства, не вывод этого теста.
    assert FAMILY_ZIP_MAX_BYTES >= 254 * 1024 * 1024

    _seed_docs_family()
    monkeypatch.setattr(
        "catalog.docs_views.family_zip_total_bytes",
        lambda files: 250 * 1024 * 1024,
    )
    buf = tempfile.SpooledTemporaryFile()  # noqa: SIM115
    buf.write(b"PK\x05\x06" + b"\x00" * 18)
    buf.seek(0)
    monkeypatch.setattr("catalog.docs_views.build_family_zip", lambda files: buf)
    response = client.get(reverse("catalog-docs-family-zip", kwargs={"key": "DA2MU"}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_docs_family_zip_rejects_an_archive_over_the_cap(client, monkeypatch) -> None:
    """Семейство больше лимита не собирается в память: 413, как у ZIP кабинета."""
    from catalog import docs_hub
    from catalog.docs_views import DocsFamilyZipView

    _seed_docs_family()
    monkeypatch.setattr(docs_hub, "FAMILY_ZIP_MAX_BYTES", 1)
    monkeypatch.setattr("catalog.docs_views.FAMILY_ZIP_MAX_BYTES", 1)
    response = client.get(reverse("catalog-docs-family-zip", kwargs={"key": "DA2MU"}))
    assert response.status_code == 413
    assert DocsFamilyZipView.throttle_scope == "docs_zip"


@pytest.mark.django_db
def test_family_zip_does_not_reuse_a_name_after_a_partial_write(settings, tmp_path) -> None:
    """Сбой чтения после открытия записи в ZIP не даёт второму файлу то же имя."""
    from catalog.docs_hub import build_family_zip
    from catalog.models import SKU, Category, Product, ProductFile

    settings.MEDIA_ROOT = str(tmp_path)
    category = Category.objects.create(name="ZIP", slug="zip-name-guard")
    product = Product.objects.create(name="ZIP", slug="zip-name-guard-p", category=category)
    sku = SKU.objects.create(
        product=product,
        sku_code="DA2MU24-D",
        name="DA2MU",
        slug="zip-name-guard-sku",
        is_published=True,
    )

    class _Broken:
        def __enter__(self) -> _Broken:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self, size: int = -1) -> bytes:
            raise OSError("disk")

        def close(self) -> None:
            return None

    broken = ProductFile(
        sku=sku,
        title="Manual One",
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
    )
    broken.file.save("broken.pdf", ContentFile(b"%PDF-broken"), save=True)
    good = ProductFile(
        sku=sku,
        title="manual-one",
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
    )
    good.file.save("good.pdf", ContentFile(b"%PDF-ok"), save=True)
    broken.file.open = lambda mode="rb": _Broken()  # type: ignore[method-assign]

    archive = build_family_zip([broken, good])
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        payloads = [zf.read(name) for name in names]
    assert len(names) == len(set(names))
    assert payloads.count(b"%PDF-ok") == 1


@pytest.mark.django_db
def test_docs_family_zip_404(client) -> None:
    response = client.get(
        reverse("catalog-docs-family-zip", kwargs={"key": "NOSUCH"}),
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_docs_hub_reads_file_sizes_once_then_from_cache(client, settings, tmp_path) -> None:
    """Хаб делал stat каждого PDF на каждый запрос; размер кэшируется по pk+updated_at+имени."""
    from unittest.mock import patch

    from django.core.cache import cache

    from catalog import docs_hub

    settings.MEDIA_ROOT = str(tmp_path)
    cache.clear()
    _seed_docs_family()
    with patch.object(docs_hub, "_file_size", wraps=docs_hub._file_size) as stat:
        first = client.get(reverse("catalog-docs")).json()
        calls_first = stat.call_count
        second = client.get(reverse("catalog-docs")).json()
    assert calls_first == len(first["files"]) > 0
    assert stat.call_count == calls_first
    assert [f["size_bytes"] for f in second["files"]] == [f["size_bytes"] for f in first["files"]]
    assert all(f["size_bytes"] > 0 for f in second["files"])


@pytest.mark.django_db
def test_sku_detail_files_use_prefetch_and_skip_unpublished(django_assert_num_queries) -> None:
    """get_files() через .filter() обходил Prefetch — лишний запрос на каждую карточку."""
    from django.db.models import Prefetch

    from catalog.models import SKU, ProductFile
    from catalog.serializers import SKUDetailSerializer

    sku_a, _ = _seed_docs_family()
    ProductFile.objects.filter(sku=sku_a, sort_order=1).update(is_published=False)
    sku = SKU.objects.prefetch_related(Prefetch("files", queryset=ProductFile.objects.all())).get(pk=sku_a.pk)
    serializer = SKUDetailSerializer(context={})
    with django_assert_num_queries(0):
        files = serializer.get_files(sku)
    assert [f["title"] for f in files] == ["Инструкция DA2MU (D/DS)"]
