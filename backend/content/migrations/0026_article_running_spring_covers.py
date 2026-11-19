"""Attach light and dark covers for the running-time article."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SLUG = "vremya-povorota-i-vozvrat-pruzhiny"
_LIGHT = _FIXTURES / "article_vremya_povorota_i_vozvrat_pruzhiny_cover.webp"
_DARK = _FIXTURES / "article_vremya_povorota_i_vozvrat_pruzhiny_cover_dark.webp"


def _attach(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    Article = apps.get_model("content", "Article")
    article = Article.objects.filter(slug=_SLUG).first()
    if article is None:
        return
    if _LIGHT.is_file():
        article.cover.save(_LIGHT.name, ContentFile(_LIGHT.read_bytes()), save=True)
    if _DARK.is_file():
        article.cover_dark.save(_DARK.name, ContentFile(_DARK.read_bytes()), save=True)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0025_article_running_vs_spring_time"),
    ]

    operations = [
        migrations.RunPython(_attach, migrations.RunPython.noop),
    ]
