"""Point the running-time article at the question people actually ask."""

from __future__ import annotations

from pathlib import Path

from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SLUG = "vremya-povorota-i-vozvrat-pruzhiny"
_TITLE = "За сколько секунд срабатывает привод с пружиной"
_EXCERPT = (
    "Спрашивают время срабатывания и ждут одну цифру. У DA5FU вкл/выкл "
    "мотор идёт до 70 с, пружина после отключения — до 20 с."
)


def _retitle(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    Article = apps.get_model("content", "Article")
    article = Article.objects.filter(slug=_SLUG).first()
    body_path = _FIXTURES / "article_vremya_povorota_i_vozvrat_pruzhiny.html"
    if article is None or not body_path.is_file():
        return
    article.title = _TITLE
    article.excerpt = _EXCERPT
    article.body = body_path.read_text(encoding="utf-8")
    article.save(update_fields=["title", "excerpt", "body", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0027_article_running_spring_plain_speech"),
    ]

    operations = [
        migrations.RunPython(_retitle, migrations.RunPython.noop),
    ]
