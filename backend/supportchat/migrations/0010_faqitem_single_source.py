"""FAQ: question_short + show_on_home; seed home block from former HOME_FAQ_ITEMS."""

from __future__ import annotations

from django.db import migrations, models

HOME_FAQ_UPDATES: tuple[dict[str, object], ...] = (
    {
        "match_question": "SA вместо DA?",
        "question": "Можно ли заменить SA10FU230-DS на DA10FU230-DS?",
        "question_short": "SA вместо DA?",
        "show_on_home": True,
    },
    {
        "match_question": "Как подобрать момент?",
        "question": "Как оценить нужный крутящий момент?",
        "question_short": "Как подобрать момент?",
        "show_on_home": True,
    },
)

HOME_FAQ_NEW: tuple[dict[str, object], ...] = (
    {
        "question": "Как заказать и получить КП?",
        "answer": (
            "Подберите модель в /catalog или опишите задачу — заявка на "
            "/consultation. Ответ до 2 рабочих часов. Партнёры: /gde-kupit."
        ),
        "order": 25,
        "show_on_home": True,
        "show_in_chat": False,
    },
    {
        "question": "Как подобрать модель на сайте?",
        "answer": (
            "На главной — блок «Подбор за минуту»: тип продукции (привод, шаровой кран, "
            "комплект, кронштейн BR-M/BR-ML), параметры из проекта → подборка в /catalog "
            "или заявка на /consultation."
        ),
        "order": 26,
        "show_on_home": True,
        "show_in_chat": False,
    },
)


def seed_home_faq(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    for row in FaqItem.objects.all().only("id", "question", "question_short"):
        short = (row.question_short or "").strip()
        if not short:
            row.question_short = row.question
            row.save(update_fields=["question_short"])

    for spec in HOME_FAQ_UPDATES:
        match = str(spec["match_question"])
        item = FaqItem.objects.filter(question=match).order_by("id").first()
        if item is None:
            item = FaqItem.objects.filter(question_short=match).order_by("id").first()
        if item is None:
            continue
        item.question = str(spec["question"])
        item.question_short = str(spec["question_short"])
        item.show_on_home = bool(spec["show_on_home"])
        item.is_active = True
        item.save(
            update_fields=["question", "question_short", "show_on_home", "is_active"],
        )

    for spec in HOME_FAQ_NEW:
        question = str(spec["question"])
        if FaqItem.objects.filter(question=question).exists():
            FaqItem.objects.filter(question=question).update(
                answer=str(spec["answer"]),
                order=int(spec["order"]),
                is_active=True,
                show_on_home=True,
                show_in_chat=bool(spec["show_in_chat"]),
            )
            continue
        FaqItem.objects.create(
            question=question,
            question_short="",
            answer=str(spec["answer"]),
            order=int(spec["order"]),
            is_active=True,
            show_on_home=True,
            show_in_chat=bool(spec["show_in_chat"]),
        )


def unseed_home_faq(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    for spec in HOME_FAQ_UPDATES:
        item = FaqItem.objects.filter(question=str(spec["question"])).order_by("id").first()
        if item is None:
            continue
        item.question = str(spec["question_short"])
        item.show_on_home = False
        item.save(update_fields=["question", "show_on_home"])
    for spec in HOME_FAQ_NEW:
        FaqItem.objects.filter(question=str(spec["question"])).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("supportchat", "0009_conversation_ai_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="faqitem",
            name="question_short",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Чип в виджете чата. Пусто — используется полный вопрос.",
                max_length=300,
                verbose_name="короткий вопрос",
            ),
        ),
        migrations.AddField(
            model_name="faqitem",
            name="show_on_home",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Показывать в секции «Частые вопросы» на главной и в JSON-LD.",
                verbose_name="блок на главной",
            ),
        ),
        migrations.AlterField(
            model_name="faqitem",
            name="question",
            field=models.CharField(
                help_text="Полная формулировка для главной, /faq и SEO.",
                max_length=300,
                verbose_name="вопрос",
            ),
        ),
        migrations.RunPython(seed_home_faq, unseed_home_faq),
    ]
