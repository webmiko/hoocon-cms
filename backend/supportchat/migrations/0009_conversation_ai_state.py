"""AI assistant state on support conversations."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("supportchat", "0008_alter_faqitem_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="ai_active",
            field=models.BooleanField(
                default=True,
                help_text="Пока True — GigaChat отвечает на входящие; False после эскалации менеджеру.",
                verbose_name="ассистент ведёт диалог",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="ai_escalated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="передан менеджеру",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="ai_turn_count",
            field=models.PositiveSmallIntegerField(
                default=0,
                verbose_name="ходов ассистента",
            ),
        ),
    ]
