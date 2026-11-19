"""Reload the running-time article in plain language."""

from __future__ import annotations

from pathlib import Path

from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SLUG = "vremya-povorota-i-vozvrat-pruzhiny"
_EXCERPT = (
    "Привод с пружиной открывает заслонку до 70 секунд, а сам возвращает её до 20. Короткая цифра — не время открытия."
)


def _reload(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    Article = apps.get_model("content", "Article")
    article = Article.objects.filter(slug=_SLUG).first()
    body_path = _FIXTURES / "article_vremya_povorota_i_vozvrat_pruzhiny.html"
    if article is None or not body_path.is_file():
        return
    article.excerpt = _EXCERPT
    article.body = body_path.read_text(encoding="utf-8")
    article.save(update_fields=["excerpt", "body", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0029_article_running_time_epos"),
    ]

    operations = [
        migrations.RunPython(_reload, migrations.RunPython.noop),
    ]
