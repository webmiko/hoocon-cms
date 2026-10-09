import re

from django.db import migrations
from django.db.models import Q

# Same rules as catalog.etl.tech_copy._REPLACEMENTS, frozen for this migration.
SPELLING_FIXES = (
    (re.compile(r"°\s*С"), "°C"),
    (
        re.compile(r"безопасное\s+низкое\s+напряжение", re.IGNORECASE),
        "безопасное сверхнизкое напряжение",
    ),
)


def unify_selv_and_degree_spelling(apps, schema_editor):
    AttributeValue = apps.get_model("catalog", "AttributeValue")
    candidates = AttributeValue.objects.filter(is_manual=False).filter(
        Q(value__regex=r"°\s*С") | Q(value__icontains="безопасное низкое"),
    )
    changed = []
    for row in candidates.iterator():
        value = row.value
        for pattern, replacement in SPELLING_FIXES:
            value = pattern.sub(replacement, value)
        if value != row.value:
            row.value = value
            changed.append(row)
    AttributeValue.objects.bulk_update(changed, ["value"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0020_unify_protection_class_ii"),
    ]

    operations = [
        migrations.RunPython(unify_selv_and_degree_spelling, migrations.RunPython.noop),
    ]
