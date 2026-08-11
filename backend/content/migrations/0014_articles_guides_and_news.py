"""Publish podbor + sertifikaty guides, schedule rest, announce in news."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.db import migrations
from django.utils import timezone

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_MSK = ZoneInfo("Europe/Moscow")

_NEWS_SLUG = "articles-podbor-i-sertifikaty"
_NEWS_TITLE = "Новые статьи: подбор привода и сертификаты CE/UL/EAC"
_NEWS_COVER = _FIXTURES / "article_podbor_privoda_cover.webp"

_NEWS_BODY = """
<p>В разделе <a href="/statyi">«Статьи»</a> — два практических материала для
подбора и приёмки электроприводов ОВК.</p>
<p><strong>Подбор по моменту.</strong>
<a href="/statyi/podbor-privoda-po-momentu-i-ploshchadi">Подбор привода по
площади и давлению</a>: как оценить крутящий момент через площадь и
перепад давления, затем перейти к ряду Н·м в каталоге.</p>
<p><strong>Сертификаты.</strong>
<a href="/statyi/sertifikaty-ce-ul-eac-elektroprivody-ovk">CE, UL и EAC для
электроприводов ОВК</a>: что сверять в карточке SKU по региону поставки и
чем знаки не заменяют расчёт момента.</p>
<p>Остальные гайды серии (типы управления, 24/230&nbsp;В, MU/MQU/HV, аналог
Belimo) выходят по расписанию.</p>
""".strip()

# slug → (title, body file, light cover, dark cover, published_at MSK)
_ARTICLES: dict[str, tuple[str, str, str, str, datetime]] = {
    "sertifikaty-ce-ul-eac-elektroprivody-ovk": (
        "CE, UL и EAC для электроприводов ОВК",
        "article_sertifikaty_ce_ul_eac.html",
        "article_sertifikaty_ce_ul_eac_cover_light.webp",
        "article_sertifikaty_ce_ul_eac_cover_dark.webp",
        datetime(2026, 8, 6, 9, 0, tzinfo=_MSK),
    ),
    "podbor-privoda-po-momentu-i-ploshchadi": (
        "Подбор привода по площади и давлению: как выбрать момент",
        "article_podbor_privoda_po_momentu.html",
        "article_podbor_privoda_cover.webp",
        "article_podbor_privoda_cover_dark.webp",
        datetime(2026, 8, 11, 9, 0, tzinfo=_MSK),
    ),
    "tipy-upravleniya-privodom": (
        "Типы управления приводом: Открыто/закрыто, 2-/3 и 0–10 В",
        "article_tipy_upravleniya_privodom.html",
        "article_tipy_upravleniya_cover.webp",
        "article_tipy_upravleniya_cover_dark.webp",
        datetime(2026, 8, 13, 9, 0, tzinfo=_MSK),
    ),
    "pitanie-24-ili-230-v": (
        "24 В или 230 В: что выбрать для электропривода",
        "article_pitanie_24_ili_230.html",
        "article_pitanie_24_230_cover.webp",
        "article_pitanie_24_230_cover_dark.webp",
        datetime(2026, 8, 15, 9, 0, tzinfo=_MSK),
    ),
    "mu-mqu-hv-kogda-nuzhen-uskorennyy": (
        "MU, MQU и HV: когда нужна ускоренная перекладка",
        "article_mu_mqu_hv.html",
        "article_mu_mqu_hv_cover.webp",
        "article_mu_mqu_hv_cover_dark.webp",
        datetime(2026, 8, 17, 9, 0, tzinfo=_MSK),
    ),
    "analog-belimo-hoocon": (
        "Замена Belimo на Hoocon: как подбирать аналог",
        "article_analog_belimo_hoocon.html",
        "article_analog_belimo_cover.webp",
        "article_analog_belimo_cover_dark.webp",
        datetime(2026, 8, 19, 9, 0, tzinfo=_MSK),
    ),
}

_EXCERPTS: dict[str, str] = {
    "sertifikaty-ce-ul-eac-elektroprivody-ovk": (
        "CE, UL и EAC для электроприводов ОВК: допуск и приёмка по региону, "
        "что сверять в карточке SKU и чем знаки не заменяют подбор момента."
    ),
    "podbor-privoda-po-momentu-i-ploshchadi": (
        "Как выбрать электропривод для заслонки: подбор по крутящему моменту "
        "через площадь и давление (ориентир), затем ряд Нм в каталоге."
    ),
    "tipy-upravleniya-privodom": (
        "Типы электроприводов для вентиляции: Открыто/закрыто, 2-/3 и "
        "пропорциональное с сигналом 0(2)…10 В=; мА — спецзаказ."
    ),
    "pitanie-24-ili-230-v": (
        "Электропривод 230 В или 24 В: как выбрать номинал по щиту и АСУ, класс защиты III/II и IP — разные оси."
    ),
    "mu-mqu-hv-kogda-nuzhen-uskorennyy": (
        "MU, MQU и HV: когда нужна скорость хода; ориентиры секунд и почему ускоренный привод не заменяет fail-safe."
    ),
    "analog-belimo-hoocon": (
        "Аналог Belimo / замена белимо на Hoocon: чеклист осей ТТХ и форма "
        "/replacement без непроверенной таблицы кроссов."
    ),
}


def _save_image(field, path: Path) -> None:  # noqa: ANN001
    """Attach WebP fixture to ImageField if the file exists."""
    if not path.is_file():
        return
    field.save(path.name, ContentFile(path.read_bytes()), save=True)


def _ensure_content(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert guide articles + announcement news from fixtures."""
    Article = apps.get_model("content", "Article")
    News = apps.get_model("content", "News")

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

    now = timezone.now()
    news, _created = News.objects.update_or_create(
        slug=_NEWS_SLUG,
        defaults={
            "title": _NEWS_TITLE,
            "body": _NEWS_BODY,
            "is_published": True,
        },
    )
    if news.published_at is None:
        news.published_at = now
        news.save(update_fields=["published_at", "updated_at"])
    if not news.cover:
        _save_image(news.cover, _NEWS_COVER)


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Keep content on reverse — rollback via Admin if needed."""
    return


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0013_merge_20260810_1721"),
    ]

    operations = [
        migrations.RunPython(_ensure_content, _noop_reverse),
    ]
