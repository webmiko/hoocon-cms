"""Staff tokens: expires_at + hashed keys (plaintext rows cleared)."""

from __future__ import annotations

from django.db import migrations, models
from django.utils import timezone


def clear_plaintext_tokens(apps, schema_editor) -> None:
    """Drop legacy plaintext tokens — managers re-login via OTP after deploy."""
    StaffAuthToken = apps.get_model("staff_api", "StaffAuthToken")
    StaffAuthToken.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("staff_api", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(clear_plaintext_tokens, migrations.RunPython.noop),
        migrations.AddField(
            model_name="staffauthtoken",
            name="expires_at",
            field=models.DateTimeField(default=timezone.now),
            preserve_default=False,
        ),
    ]
