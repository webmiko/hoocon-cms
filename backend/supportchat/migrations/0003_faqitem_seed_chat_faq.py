"""FAQ чата: модель FaqItem и 5 стартовых вопросов из /faq."""

from __future__ import annotations

from django.db import migrations, models

FAQ_ITEMS: tuple[tuple[str, str, int], ...] = (
    (
        "Площадь круглого клапана?",
        (
            "Для диаметра 20 см (0,2 м): радиус 0,1 м, S = π × r² ≈ 3,14 × 0,01 = "
            "0,0314 м². Всегда переводите размеры в метры. Площадь сечения задаёт "
            "пропускную способность в расчётах вентиляции и ПБ."
        ),
        10,
    ),
    (
        "SA вместо DA?",
        (
            "Нет. SA — для огнезадерживающих клапанов (НО ОЗК): пружина закрывает "
            "заслонку за ≤ 25 с без питания, серия испытана на работу при высоких "
            "температуре и влажности. DA — для общеобменной вентиляции, эти "
            "параметры не нормированы. Замена нарушает требования пожарной "
            "безопасности. Для ОЗК используйте серию SA или сертифицированный "
            "аналог."
        ),
        20,
    ),
    (
        "Как подобрать момент?",
        (
            "Учитывайте давление в системе (Па), тип и конструкцию заслонки, "
            "условия среды. Ориентир: M ≈ (D³ × P × k) / C, где D — диаметр или "
            "большая сторона (м), P — давление (Па), k — коэффициент типа "
            "заслонки (примерно 0,5–3,0), C — эмпирический коэффициент "
            "(часто 2000–4000). Для проекта сверяйте таблицы производителя "
            "заслонки и паспорт привода в каталоге на сайте."
        ),
        30,
    ),
    (
        "Сигнал 4–20 мА?",
        (
            "Заводская установка пропорциональных приводов — сигнал напряжения "
            "0(2)...10 В= (по умолчанию 0...10 В=). Режим тока 0(4)...20 мА "
            "доступен только по спецзаказу: переключение DIP / заводская "
            "конфигурация под ваш контроллер. Укажите требование к току в заявке "
            "на КП — менеджер уточнит срок и исполнение."
        ),
        40,
    ),
    (
        "Что такое fail-safe?",
        (
            "Fail-safe (аварийный возврат) — при пропадании питания привод сам "
            "уводит заслонку в безопасное положение. FU — пружиной (механический "
            "возврат), EU — электронной схемой без пружины. Без fail-safe привод "
            "остаётся в текущем положении."
        ),
        50,
    ),
    (
        "Где купить?",
        (
            "Юрлица заказывают напрямую у ООО «Хогон»: 8 800 350-58-98, "
            "sales@hoocon.ru (склад в МО) или /consultation. "
            "Физлицам удобнее к партнёрам в своём городе — Москва, СПб, "
            "Минск и др. Полный список партнёров — /gde-kupit"
        ),
        60,
    ),
)


def seed_faq_items(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    for question, answer, order in FAQ_ITEMS:
        item = FaqItem.objects.filter(question=question).order_by("id").first()
        if item is None:
            FaqItem.objects.create(
                question=question,
                answer=answer,
                order=order,
                is_active=True,
                show_in_chat=True,
            )
            continue
        current = (item.answer or "").strip()
        if not current:
            item.answer = answer
            item.order = order
            item.is_active = True
            item.show_in_chat = True
            item.save(
                update_fields=["answer", "order", "is_active", "show_in_chat"],
            )


def unseed_faq_items(apps, schema_editor) -> None:
    FaqItem = apps.get_model("supportchat", "FaqItem")
    for question, answer, _order in FAQ_ITEMS:
        FaqItem.objects.filter(question=question, answer=answer).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("supportchat", "0002_seed_schedule"),
    ]

    operations = [
        migrations.CreateModel(
            name="FaqItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("question", models.CharField(max_length=300, verbose_name="вопрос")),
                ("answer", models.TextField(verbose_name="ответ")),
                (
                    "order",
                    models.PositiveIntegerField(default=0, verbose_name="порядок"),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="активен",
                    ),
                ),
                (
                    "show_in_chat",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text="Показывать вопрос чипом в виджете чата на сайте.",
                        verbose_name="быстрая кнопка в чате",
                    ),
                ),
            ],
            options={
                "verbose_name": "вопрос FAQ",
                "verbose_name_plural": "FAQ чата",
                "ordering": ("order", "id"),
            },
        ),
        migrations.RunPython(seed_faq_items, unseed_faq_items),
    ]
