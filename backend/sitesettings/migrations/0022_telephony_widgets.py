from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sitesettings", "0021_client_next_contact_quote_vat_rop_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="mango_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Выкл — вебхук и звонок из карточки клиента не ходят в Mango, даже если ключи заданы.",
                verbose_name="Mango включён",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="mango_api_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Пустое поле не стирает сохранённый ключ. Запасной вариант: MANGO_VPBX_API_KEY.",
                max_length=200,
                verbose_name="ключ API Mango",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="mango_api_salt",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Пустое поле не стирает сохранённую соль. Запасной вариант: MANGO_VPBX_API_SALT.",
                max_length=200,
                verbose_name="соль API Mango",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="mango_callback_webhook_url",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Шаблон из ЛК Mango. Плейсхолдеры {ext} и {num}. Пусто — MANGO_CALLBACK_WEBHOOK_URL.",
                max_length=500,
                verbose_name="URL вебхука исходящего звонка Mango",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="novosystem_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Выкл — вебхук UIS и звонок из карточки не используются.",
                verbose_name="Новосистем включён",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="novosystem_access_token",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Постоянный ключ пользователя UIS с доступом к Call API. Пустое поле не стирает ключ.",
                max_length=200,
                verbose_name="ключ API Новосистем",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="novosystem_virtual_phone",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Номер в формате E.164 без плюса, например 74951234567. С него идут исходящие.",
                max_length=20,
                verbose_name="виртуальный номер Новосистем",
            ),
        ),
        migrations.AddField(
            model_name="sitesettings",
            name="novosystem_webhook_secret",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Добавьте его в URL уведомления UIS как token. Пустое поле не стирает секрет.",
                max_length=80,
                verbose_name="секрет вебхука Новосистем",
            ),
        ),
    ]
