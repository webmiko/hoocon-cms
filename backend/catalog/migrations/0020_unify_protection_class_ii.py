from django.db import migrations

OLD_SPELLINGS = (
    "II (все изолировано / полная изоляция)",
    "II (всё изолировано / полная изоляция)",
)
PROTECTION_CLASS_II = "II (полная изоляция)"


def unify_protection_class_ii(apps, schema_editor):
    AttributeValue = apps.get_model("catalog", "AttributeValue")
    AttributeValue.objects.filter(
        attribute__slug="protection-class",
        value__in=OLD_SPELLINGS,
        is_manual=False,
    ).update(value=PROTECTION_CLASS_II)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0019_etl_manual_edit_flags"),
    ]

    operations = [
        migrations.RunPython(unify_protection_class_ii, migrations.RunPython.noop),
    ]
