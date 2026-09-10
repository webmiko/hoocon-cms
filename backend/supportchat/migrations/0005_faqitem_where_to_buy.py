"""Добавил FAQ «Где купить?» для чипа в виджете чата."""

from __future__ import annotations

from django.db import migrations

QUESTION = "Где купить?"
ANSWER = (
    "Юрлица заказывают напрямую у ООО «Хогон»: 8 800 350-58-98, "
    "sales@hoocon.ru (склад в МО) или /consultation. "
    "Физлицам удобнее к партнёрам в своём городе — Москва, СПб, "
    "Минск и др. Полный список партнёров — /gde-kupit"
)
ORDER = 60


def add_where_to_buy(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    item = FaqItem.objects.filter(question=QUESTION).order_by("id").first()
    if item is None:
        FaqItem.objects.create(
            question=QUESTION,
            answer=ANSWER,
            order=ORDER,
            is_active=True,
            show_in_chat=True,
        )
        return
    current = (item.answer or "").strip()
    if not current:
        item.answer = ANSWER
    item.order = ORDER
    item.is_active = True
    item.show_in_chat = True
    item.save(update_fields=["answer", "order", "is_active", "show_in_chat"])


def remove_where_to_buy(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    FaqItem.objects.filter(question=QUESTION, answer=ANSWER).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("supportchat", "0004_faqitem_short_questions"),
    ]

    operations = [
        migrations.RunPython(add_where_to_buy, remove_where_to_buy),
    ]
