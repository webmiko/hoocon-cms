"""GigaChat assistant toggles on SiteSettings."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sitesettings", "0016_max_admin_ru_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="gigachat_enabled",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Первичные ответы в support-чате через GigaChat API. "
                    "Нужен Authorization Key (Admin или GIGACHAT_CREDENTIALS в .env)."
                ),
                verbose_name="GigaChat-ассистент в чате",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="gigachat_credentials",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Authorization Key из Studio. Пустое поле при сохранении не стирает ключ. "
                    "Запасной вариант: GIGACHAT_CREDENTIALS в .env."
                ),
                max_length=500,
                verbose_name="ключ GigaChat (Authorization Key)",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="gigachat_model",
            field=models.CharField(
                blank=True,
                default="GigaChat-2",
                max_length=64,
                verbose_name="модель GigaChat",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="ai_max_turns",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="После N ответов бота диалог передаётся менеджеру.",
                verbose_name="лимит ответов ассистента",
            ),
        ),
    ]
