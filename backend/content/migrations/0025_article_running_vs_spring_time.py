"""Publish the running-time vs spring-return guide and refresh the FU link."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_MSK = ZoneInfo("Europe/Moscow")
_SLUG = "vremya-povorota-i-vozvrat-pruzhiny"
_TITLE = "За сколько секунд срабатывает привод с пружиной"
_EXCERPT = (
    "Спрашивают время срабатывания и ждут одну цифру. У DA5FU вкл/выкл "
    "мотор идёт до 70 с, пружина после отключения — до 20 с."
)
_GO_LIVE = datetime(2026, 11, 20, 9, 0, tzinfo=_MSK)


def _publish(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    Article = apps.get_model("content", "Article")
    body_path = _FIXTURES / "article_vremya_povorota_i_vozvrat_pruzhiny.html"
    if body_path.is_file():
        Article.objects.update_or_create(
            slug=_SLUG,
            defaults={
                "title": _TITLE,
                "body": body_path.read_text(encoding="utf-8"),
                "excerpt": _EXCERPT,
                "is_published": True,
                "published_at": _GO_LIVE,
            },
        )
    fu_path = _FIXTURES / "article_fu_vs_eu_fail_safe.html"
    fu = Article.objects.filter(slug="fu-vs-eu-fail-safe").first()
    if fu is not None and fu_path.is_file():
        fu.body = fu_path.read_text(encoding="utf-8")
        fu.save(update_fields=["body", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0024_news_airvent_2027_cover_with_dates"),
    ]

    operations = [
        migrations.RunPython(_publish, migrations.RunPython.noop),
    ]
