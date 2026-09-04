"""Seed P2 selection guides with staggered published_at (Iter C+D)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_MSK = ZoneInfo("Europe/Moscow")

# slug → (title, body file, light cover, dark cover, published_at MSK)
_ARTICLES: dict[str, tuple[str, str, str, str, datetime]] = {
    "suffiksy-d-a-s-t": (
        "Суффиксы D, A, S и T в артикуле электропривода",
        "article_suffiksy_d_a_s_t.html",
        "article_suffiksy_d_a_s_t_cover.webp",
        "article_suffiksy_d_a_s_t_cover_dark.webp",
        datetime(2026, 9, 7, 9, 0, tzinfo=_MSK),
    ),
    "fu-vs-eu-fail-safe": (
        "Пружина FU или электронный EU: какой fail-safe выбрать",
        "article_fu_vs_eu_fail_safe.html",
        "article_fu_vs_eu_fail_safe_cover.webp",
        "article_fu_vs_eu_fail_safe_cover_dark.webp",
        datetime(2026, 9, 14, 9, 0, tzinfo=_MSK),
    ),
    "vspomogatelnyy-pereklyuchatel": (
        "Вспомогательный переключатель S: DS, AS и DST",
        "article_vspomogatelnyy_pereklyuchatel.html",
        "article_vspomogatelnyy_pereklyuchatel_cover.webp",
        "article_vspomogatelnyy_pereklyuchatel_cover_dark.webp",
        datetime(2026, 9, 21, 9, 0, tzinfo=_MSK),
    ),
    "komplekt-sharovoy-kran-privod": (
        "Комплект шаровой кран + электропривод: когда брать H81",
        "article_komplekt_sharovoy_kran_privod.html",
        "article_komplekt_sharovoy_kran_privod_cover.webp",
        "article_komplekt_sharovoy_kran_privod_cover_dark.webp",
        datetime(2026, 9, 28, 9, 0, tzinfo=_MSK),
    ),
    "pasport-i-sertifikaty-v-zayavke": (
        "Паспорт и сертификаты в заявке: короткий чек‑лист",
        "article_pasport_i_sertifikaty_v_zayavke.html",
        "article_pasport_i_sertifikaty_v_zayavke_cover.webp",
        "article_pasport_i_sertifikaty_v_zayavke_cover_dark.webp",
        datetime(2026, 10, 5, 9, 0, tzinfo=_MSK),
    ),
}

_EXCERPTS: dict[str, str] = {
    "suffiksy-d-a-s-t": (
        "Суффиксы D, A, S и T в артикуле электропривода Hoocon: управление, "
        "вспомогательный переключатель и термодатчик — без путаницы с FU/EU."
    ),
    "fu-vs-eu-fail-safe": (
        "Fail-safe электропривода: пружина FU vs электронный EU; когда нужен "
        "аварийный возврат и почему SA…FU нельзя менять на DA…MU."
    ),
    "vspomogatelnyy-pereklyuchatel": (
        "Вспомогательный переключатель S (SPDT): зачем DS/AS, чем DST отличается "
        "на ОЗК и как не путать T с трёхпозиционным управлением."
    ),
    "komplekt-sharovoy-kran-privod": (
        "Комплект шаровой кран + привод H81 или корпус 8100/8100Q отдельно: "
        "что согласовать по DN, Kvs, питанию и сигналу."
    ),
    "pasport-i-sertifikaty-v-zayavke": (
        "Что приложить к ПБ и заявке на привод: паспорт, CE/UL/EAC, шильдик и "
        "параметры сигнала — короткий чек‑лист снабжения."
    ),
}


def _save_image(field, path: Path) -> None:  # noqa: ANN001
    """Attach WebP fixture to ImageField if the file exists."""
    if not path.is_file():
        return
    field.save(path.name, ContentFile(path.read_bytes()), save=True)


def _ensure_content(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert P2 guide articles from fixtures."""
    Article = apps.get_model("content", "Article")

    for slug, (title, body_name, light, dark, go_live) in _ARTICLES.items():
        body_path = _FIXTURES / body_name
        if not body_path.is_file():
            continue
        body = body_path.read_text(encoding="utf-8")
        excerpt = _EXCERPTS.get(slug, "")
        article, _created = Article.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "body": body,
                "excerpt": excerpt,
                "is_published": True,
                "published_at": go_live,
            },
        )
        _save_image(article.cover, _FIXTURES / light)
        _save_image(article.cover_dark, _FIXTURES / dark)


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Keep content on reverse — rollback via Admin if needed."""
    return


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0016_news_category"),
    ]

    operations = [
        migrations.RunPython(_ensure_content, _noop_reverse),
    ]
