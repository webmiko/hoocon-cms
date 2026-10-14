from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_staffvpbxprofile_uis_webrtc_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staffvpbxprofile",
            name="uis_employee_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Числовой id сотрудника в Новосистем (UIS). Один id — один сотрудник. "
                    "Нужен для звонка из карточки, когда виджет включён."
                ),
                max_length=20,
                verbose_name="ID сотрудника UIS",
            ),
        ),
        migrations.AddConstraint(
            model_name="staffvpbxprofile",
            constraint=models.UniqueConstraint(
                condition=models.Q(("uis_employee_id", ""), _negated=True),
                fields=("uis_employee_id",),
                name="accounts_staffvpbx_uis_employee_uniq",
            ),
        ),
    ]
