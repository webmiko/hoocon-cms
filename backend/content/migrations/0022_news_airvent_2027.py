"""Publish AIRVent 2027 participation news + exhibition cover."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations
from django.utils import timezone

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_NEWS_SLUG = "hoocon-airvent-2027"
_NEWS_TITLE = "AIRVent 2027: участие Hoocon"
_NEWS_COVER = _FIXTURES / "news_airvent_2027_cover.webp"
_PHONE = "8 800 350-58-98"
_EMAIL = "sales@hoocon.ru"

_NEWS_BODY = f"""
<p>Компания <strong>Hoocon</strong> (ООО «Хогон») планирует участие в
международной выставке <strong>AIRVent&nbsp;2027</strong> — отраслевом форуме
по вентиляции, кондиционированию и холодоснабжению жилых, коммерческих и
промышленных объектов.</p>
<p><strong>Когда и где.</strong> 1–4&nbsp;февраля 2027&nbsp;года, Москва,
МВЦ «Крокус Экспо», павильон&nbsp;3, зал&nbsp;15. Регистрация и программа —
на сайте
<a href="https://airventmoscow.ru/ru/" rel="noopener noreferrer" target="_blank">AIRVent</a>.</p>
<p><strong>Стенд.</strong> Номер нашего стенда и расположение на плане
выставки опубликуем позже — эту новость обновим, когда организаторы выдадут
площадку.</p>
<p>Ближе к датам дополним программу встречи на стенде. Вопросы по продукции и
встрече на выставке — через <a href="/consultation">заявку на КП</a>,
по телефону {_PHONE} или
<a href="mailto:{_EMAIL}">{_EMAIL}</a>.</p>
<p><a href="/kontakty">Контакты Hoocon</a></p>
""".strip()


def _ensure_news(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert hoocon-airvent-2027, attach cover, assign «Мероприятия»."""
    News = apps.get_model("content", "News")
    NewsCategory = apps.get_model("content", "NewsCategory")

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

    if not news.cover and _NEWS_COVER.is_file():
        news.cover.save(
            _NEWS_COVER.name,
            ContentFile(_NEWS_COVER.read_bytes()),
            save=True,
        )

    category = NewsCategory.objects.filter(slug="meropriyatiya").first()
    if category is not None and news.category_id != category.pk:
        news.category = category
        news.save(update_fields=["category", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0021_wikidocument_seed_hash"),
    ]

    operations = [
        migrations.RunPython(_ensure_news, migrations.RunPython.noop),
    ]
