from django.db import migrations

_CODENAMES = {
    "add_staffvpbxprofile": "Can add Телефония сотрудника",
    "change_staffvpbxprofile": "Can change Телефония сотрудника",
    "delete_staffvpbxprofile": "Can delete Телефония сотрудника",
    "view_staffvpbxprofile": "Can view Телефония сотрудника",
}

_PREVIOUS = {
    "add_staffvpbxprofile": "Can add Добавочный сотрудника (Mango)",
    "change_staffvpbxprofile": "Can change Добавочный сотрудника (Mango)",
    "delete_staffvpbxprofile": "Can delete Добавочный сотрудника (Mango)",
    "view_staffvpbxprofile": "Can view Добавочный сотрудника (Mango)",
}


def _rename(apps, names: dict[str, str]) -> None:
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    content_type = ContentType.objects.filter(app_label="accounts", model="staffvpbxprofile").first()
    if content_type is None:
        return
    for codename, name in names.items():
        Permission.objects.filter(content_type=content_type, codename=codename).update(name=name)


def rename_staff_telephony_permissions(apps, schema_editor) -> None:
    _rename(apps, _CODENAMES)


def restore_staff_telephony_permissions(apps, schema_editor) -> None:
    _rename(apps, _PREVIOUS)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_drop_mango_admin_labels"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(rename_staff_telephony_permissions, restore_staff_telephony_permissions),
    ]
