"""Replace AIRVent 2027 news cover with official exhibition og:image."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_NEWS_SLUG = "hoocon-airvent-2027"
_NEWS_COVER = _FIXTURES / "news_airvent_2027_cover.webp"


def _refresh_cover(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Re-attach cover from fixture (official AV27 social preview)."""
    if not _NEWS_COVER.is_file():
        return
    News = apps.get_model("content", "News")
    news = News.objects.filter(slug=_NEWS_SLUG).first()
    if news is None:
        return
    news.cover.save(
        _NEWS_COVER.name,
        ContentFile(_NEWS_COVER.read_bytes()),
        save=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0022_news_airvent_2027"),
    ]

    operations = [
        migrations.RunPython(_refresh_cover, migrations.RunPython.noop),
    ]
