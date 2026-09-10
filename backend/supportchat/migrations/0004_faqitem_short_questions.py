"""Сократил формулировки вопросов FAQ для чипов в виджете чата."""

from __future__ import annotations

from django.db import migrations

QUESTION_RENAMES: tuple[tuple[str, str], ...] = (
    (
        "Как рассчитать площадь сечения круглого клапана?",
        "Площадь круглого клапана?",
    ),
    (
        "Можно ли заменить SA10FU230-DS на DA10FU230-DS?",
        "SA вместо DA?",
    ),
    (
        "Как оценить нужный крутящий момент?",
        "Как подобрать момент?",
    ),
    (
        "Что значит 0(4)...20 мА (спецзаказ)?",
        "Сигнал 4–20 мА?",
    ),
    (
        "Что такое fail-safe у привода?",
        "Что такое fail-safe?",
    ),
)


def shorten_questions(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    for old, new in QUESTION_RENAMES:
        FaqItem.objects.filter(question=old).update(question=new)


def restore_long_questions(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    for old, new in QUESTION_RENAMES:
        FaqItem.objects.filter(question=new).update(question=old)


class Migration(migrations.Migration):
    dependencies = [
        ("supportchat", "0003_faqitem_seed_chat_faq"),
    ]

    operations = [
        migrations.RunPython(shorten_questions, restore_long_questions),
    ]
