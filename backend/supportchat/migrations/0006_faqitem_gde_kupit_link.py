"""Обновил ответ «Где купить?» — ссылка на /gde-kupit."""

from __future__ import annotations

from django.db import migrations

QUESTION = "Где купить?"
ANSWER = (
    "Юрлица заказывают напрямую у ООО «Хогон»: 8 800 350-58-98, "
    "sales@hoocon.ru (склад в МО) или /consultation. "
    "Физлицам удобнее к партнёрам в своём городе — Москва, СПб, "
    "Минск и др. Полный список партнёров — /gde-kupit"
)


def update_answer(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    FaqItem.objects.filter(question=QUESTION).update(answer=ANSWER)


def noop(apps, schema_editor) -> None:
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("supportchat", "0005_faqitem_where_to_buy"),
    ]

    operations = [
        migrations.RunPython(update_answer, noop),
    ]
