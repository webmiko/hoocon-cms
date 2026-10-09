from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_private_chat_attachments_signed_imap"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffvpbxprofile",
            name="uis_employee_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Числовой id сотрудника в Новосистем (UIS). Нужен для звонка из карточки, когда виджет включён.",
                max_length=20,
                verbose_name="ID сотрудника UIS",
            ),
        ),
    ]
