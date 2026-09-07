"""Enable lead round-robin: off → assign_manager (email to manager)."""

from django.db import migrations

_OFF = "off"
_ASSIGN_MANAGER = "assign_manager"


def enable_assign_manager(apps, schema_editor):
    """Turn on manager assignment when routing is still off.

    Leaves assign_sales / assign_manager unchanged (manual Admin choice wins).
    """
    SiteSettings = apps.get_model("sitesettings", "SiteSettings")
    obj, _created = SiteSettings.objects.get_or_create(pk=1)
    if obj.lead_routing_mode == _OFF:
        obj.lead_routing_mode = _ASSIGN_MANAGER
        obj.save(update_fields=["lead_routing_mode", "updated_at"])


def revert_to_off(apps, schema_editor):
    """Reverse only if still on assign_manager (do not clobber assign_sales)."""
    SiteSettings = apps.get_model("sitesettings", "SiteSettings")
    SiteSettings.objects.filter(pk=1, lead_routing_mode=_ASSIGN_MANAGER).update(
        lead_routing_mode=_OFF,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("sitesettings", "0009_lead_routing_active_help_text"),
    ]

    operations = [
        migrations.RunPython(enable_assign_manager, revert_to_off),
    ]
