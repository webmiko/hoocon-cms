"""Reschedule P2 selection guides to weekly Mondays 09:00 MSK."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations

_MSK = ZoneInfo("Europe/Moscow")

# slug → published_at (Mondays, weekly)
_GO_LIVE: dict[str, datetime] = {
    "suffiksy-d-a-s-t": datetime(2026, 9, 7, 9, 0, tzinfo=_MSK),
    "fu-vs-eu-fail-safe": datetime(2026, 9, 14, 9, 0, tzinfo=_MSK),
    "vspomogatelnyy-pereklyuchatel": datetime(2026, 9, 21, 9, 0, tzinfo=_MSK),
    "komplekt-sharovoy-kran-privod": datetime(2026, 9, 28, 9, 0, tzinfo=_MSK),
    "pasport-i-sertifikaty-v-zayavke": datetime(2026, 10, 5, 9, 0, tzinfo=_MSK),
}


def _reschedule(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Update published_at for P2 guides already seeded by 0017."""
    Article = apps.get_model("content", "Article")
    for slug, go_live in _GO_LIVE.items():
        Article.objects.filter(slug=slug).update(published_at=go_live)


def _noop_reverse(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Keep new schedule on reverse — rollback dates via Admin if needed."""
    return


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0018_refresh_p2_hv_covers"),
    ]

    operations = [
        migrations.RunPython(_reschedule, _noop_reverse),
    ]
