"""Refresh P2 actuator article covers from HVA-10 studio fixtures."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import migrations

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

_COVERS: dict[str, tuple[str, str]] = {
    "suffiksy-d-a-s-t": (
        "article_suffiksy_d_a_s_t_cover.webp",
        "article_suffiksy_d_a_s_t_cover_dark.webp",
    ),
    "fu-vs-eu-fail-safe": (
        "article_fu_vs_eu_fail_safe_cover.webp",
        "article_fu_vs_eu_fail_safe_cover_dark.webp",
    ),
    "vspomogatelnyy-pereklyuchatel": (
        "article_vspomogatelnyy_pereklyuchatel_cover.webp",
        "article_vspomogatelnyy_pereklyuchatel_cover_dark.webp",
    ),
}


def _save_image(field, path: Path) -> None:  # noqa: ANN001
    if not path.is_file():
        return
    field.save(path.name, ContentFile(path.read_bytes()), save=True)


def _refresh_covers(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    Article = apps.get_model("content", "Article")
    for slug, (light, dark) in _COVERS.items():
        article = Article.objects.filter(slug=slug).first()
        if article is None:
            continue
        _save_image(article.cover, _FIXTURES / light)
        _save_image(article.cover_dark, _FIXTURES / dark)


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    return


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0017_articles_p2_selection_guides"),
    ]

    operations = [
        migrations.RunPython(_refresh_covers, _noop_reverse),
    ]
