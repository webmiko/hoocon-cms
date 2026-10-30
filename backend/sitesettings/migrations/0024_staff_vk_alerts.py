from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sitesettings", "0023_rop_report_email_unused"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="staff_vk_leads_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Личные сообщения от сообщества Hoocon, если у сотрудника нет активных браузерных уведомлений. Нужен ид. VK в карточке (/chatid в чате).",
                verbose_name="VK при новой заявке (если нет уведомлений на устройстве)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="staff_vk_support_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Входящий чат → VK менеджерам с привязанным ид. VK и кнопкой «Ответить».",
                verbose_name="VK при сообщении в поддержке",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="staff_vk_superuser_crm_enabled",
            field=models.BooleanField(
                default=True,
                help_text="CRM-события супер-админам без активных браузерных уведомлений.",
                verbose_name="VK супер-админу по CRM (если нет уведомлений на устройстве)",
            ),
        ),
    ]
