"""Reload the running-time article after the plain-speech rewrite."""

from __future__ import annotations

from pathlib import Path

from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SLUG = "vremya-povorota-i-vozvrat-pruzhiny"
_EXCERPT = (
    "Спрашивают время срабатывания и ждут одну цифру. У DA5FU вкл/выкл "
    "мотор идёт до 70 с, пружина после отключения — до 20 с."
)


def _reload(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    Article = apps.get_model("content", "Article")
    article = Article.objects.filter(slug=_SLUG).first()
    body_path = _FIXTURES / "article_vremya_povorota_i_vozvrat_pruzhiny.html"
    if article is None or not body_path.is_file():
        return
    article.body = body_path.read_text(encoding="utf-8")
    article.excerpt = _EXCERPT
    article.save(update_fields=["body", "excerpt", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0026_article_running_spring_covers"),
    ]

    operations = [
        migrations.RunPython(_reload, migrations.RunPython.noop),
    ]
