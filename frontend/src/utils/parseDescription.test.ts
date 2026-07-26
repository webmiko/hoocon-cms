import { describe, expect, it } from "vitest";

import {
  descriptionHeadingLevel,
  instructionHeadingLevel,
  parseDescription,
  parseInstructions,
  parseProductDescription,
} from "./parseDescription";

describe("parseDescription", () => {
  it("treats long colon titles (over 60 chars) as section headings", () => {
    const title =
      "Схема подключения (см. также чертёж «Схема подключения» в галерее и PDF):";
    expect(title.replace(/:$/, "").length).toBeGreaterThan(60);
    const blocks = parseDescription(
      [title, "", "– Подключите провода к клеммам питания"].join("\n"),
    );
    expect(blocks[0]).toEqual({
      type: "section",
      title: title.replace(/:$/, ""),
    });
    expect(blocks[1]).toEqual({
      type: "list",
      items: ["Подключите провода к клеммам питания"],
    });
  });

  it("joins soft-wrapped bullet continuations into one list item", () => {
    const blocks = parseDescription(
      [
        "Инструменты:",
        "– Ключи для фиксации адаптера, отвёртка для подключения проводов,",
        "  мультиметр для проверки напряжения.",
        "– Подберите модель по крутящему моменту (3–20 Нм) и площади заслонки",
        "  (см. таблицу характеристик выбранного артикула).",
      ].join("\n"),
    );
    expect(blocks).toEqual([
      { type: "section", title: "Инструменты" },
      {
        type: "list",
        items: [
          "Ключи для фиксации адаптера, отвёртка для подключения проводов, мультиметр для проверки напряжения.",
          "Подберите модель по крутящему моменту (3–20 Нм) и площади заслонки (см. таблицу характеристик выбранного артикула).",
        ],
      },
    ]);
  });

  it("does not swallow nested chapter headings after a bullet", () => {
    const blocks = parseDescription(
      ["– Закрепите привод согласно схеме монтажа", "2.2 Подключение электропитания"].join(
        "\n",
      ),
    );
    expect(blocks.map((b) => b.type)).toEqual(["list", "paragraph"]);
    expect(blocks[0]).toEqual({
      type: "list",
      items: ["Закрепите привод согласно схеме монтажа"],
    });
  });

  it("treats bare section titles without colon as headings", () => {
    const blocks = parseDescription(
      [
        "Электропривод HVD представляет собой надёжное устройство.",
        "",
        "Области применения",
        "",
        "– Системы вентиляции",
        "",
        "Преимущества",
        "",
        "– Высокая надёжность конструкции",
      ].join("\n"),
    );
    expect(blocks.map((b) => b.type)).toEqual([
      "paragraph",
      "section",
      "list",
      "section",
      "list",
    ]);
    expect(blocks[1]).toMatchObject({
      type: "section",
      title: "Области применения",
    });
    expect(blocks[3]).toMatchObject({ type: "section", title: "Преимущества" });
  });

  it("recognizes marketing section titles as headings", () => {
    const blocks = parseDescription(
      [
        "Привод Hoocon DA..MU представляет собой электромеханический привод.",
        "",
        "Технические возможности:",
        "",
        "Функциональные особенности",
        "",
        "– Пропорциональное управление",
        "",
        "Отличительные преимущества",
        "",
        "– Надёжность конструкции",
        "",
        "Конкурентные преимущества перед аналогами",
        "",
        "– Низкое энергопотребление",
      ].join("\n"),
    );
    expect(blocks.map((b) => b.type)).toEqual([
      "paragraph",
      "section",
      "section",
      "list",
      "section",
      "list",
      "section",
      "list",
    ]);
    expect(blocks[2]).toMatchObject({
      type: "section",
      title: "Функциональные особенности",
    });
  });

  it("assigns h2 chapters and h3 subsections for install instructions", () => {
    expect(instructionHeadingLevel("ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ")).toBeNull();
    expect(instructionHeadingLevel("1. ПОДГОТОВКА К МОНТАЖУ")).toBe(2);
    expect(instructionHeadingLevel("2. ТРЕБОВАНИЯ К МОНТАЖУ")).toBe(2);
    expect(instructionHeadingLevel("3.1 Монтаж на заслонку")).toBe(3);
    expect(instructionHeadingLevel("7.2 Требуется")).toBe(3);
    expect(instructionHeadingLevel("– Пункт списка")).toBeNull();
  });

  it("keeps intro as quote paragraph; chapters h2; colon titles h3", () => {
    const blocks = parseInstructions(
      [
        "ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ",
        "Для корректной работы соблюдайте рекомендации.",
        "",
        "1. ПОДГОТОВКА К МОНТАЖУ",
        "",
        "Проверка совместимости:",
        "",
        "– Убедитесь, что вал заслонки соответствует требованиям:",
        "– Длина вала: ≥90 мм",
        "",
        "2. ТРЕБОВАНИЯ К МОНТАЖУ",
        "",
        "3. ЭТАПЫ УСТАНОВКИ",
        "",
        "3.1 Монтаж на заслонку",
        "",
        "– Закрепите привод",
      ].join("\n"),
    );
    expect(blocks).toEqual([
      {
        type: "paragraph",
        text: "ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ",
      },
      {
        type: "paragraph",
        text: "Для корректной работы соблюдайте рекомендации.",
      },
      { type: "section", title: "1. ПОДГОТОВКА К МОНТАЖУ", level: 2 },
      { type: "section", title: "1.1 Проверка совместимости", level: 3 },
      {
        type: "list",
        items: [
          "Убедитесь, что вал заслонки соответствует требованиям:",
          "Длина вала: ≥90 мм",
        ],
      },
      { type: "section", title: "2. ТРЕБОВАНИЯ К МОНТАЖУ", level: 2 },
      { type: "section", title: "3. ЭТАПЫ УСТАНОВКИ", level: 2 },
      { type: "section", title: "3.1 Монтаж на заслонку", level: 3 },
      { type: "list", items: ["Закрепите привод"] },
    ]);
  });

  it("merges incomplete «… при:» lead with following bullets into full list items", () => {
    const blocks = parseInstructions(
      [
        "2. Автоматические режимы работы",
        "",
        "Аварийное закрытие при пожаре:",
        "",
        "Срабатывание возвратной пружины (≤25 сек) при:",
        "– Отключении питания.",
        "– Сигнале от пожарной системы.",
        "– Активации термодатчика +72°C (в моделях с суффиксом DST).",
        "– Восстановление после пожара: Подача напряжения открывает заслонку.",
      ].join("\n"),
    );
    const titles = blocks
      .filter((b) => b.type === "section")
      .map((b) => (b as { title: string }).title);
    expect(titles).toEqual([
      "2. Автоматические режимы работы",
      "2.1 Аварийное закрытие при пожаре",
    ]);
    expect(titles.some((t) => t.includes("Срабатывание"))).toBe(false);
    const list = blocks.find((b) => b.type === "list") as { items: string[] };
    expect(list.items[0]).toBe(
      "Срабатывание возвратной пружины (≤25 сек) при отключении питания.",
    );
    expect(list.items[1]).toBe(
      "Срабатывание возвратной пружины (≤25 сек) при сигнале от пожарной системы.",
    );
    expect(list.items[2]).toContain("при активации термодатчика");
    const restore = blocks.filter((b) => b.type === "list").flatMap((b) =>
      b.type === "list" ? b.items : [],
    );
    expect(restore.some((i) => i.startsWith("Восстановление после пожара:"))).toBe(
      true,
    );
  });

  it("numbers bare h3 under numbered h2 as N.1 N.2", () => {
    const blocks = parseInstructions(
      [
        "1. Подготовка к установке",
        "",
        "Проверка совместимости:",
        "",
        "– Длина вала: > 50 мм",
        "",
        "Инструменты:",
        "",
        "– Мультиметр",
        "",
        "2. Монтаж привода",
        "",
        "Крепление на вал:",
        "",
        "– Закрепите привод",
      ].join("\n"),
    );
    expect(
      blocks.filter((b) => b.type === "section").map((b) => (b as { title: string }).title),
    ).toEqual([
      "1. Подготовка к установке",
      "1.1 Проверка совместимости",
      "1.2 Инструменты",
      "2. Монтаж привода",
      "2.1 Крепление на вал",
    ]);
  });

  it("assigns h2 majors and h3 numbered features in product description", () => {
    expect(descriptionHeadingLevel("Ключевые характеристики")).toBe(2);
    expect(descriptionHeadingLevel("Например")).toBeNull();
    expect(descriptionHeadingLevel("Режимы:")).toBeNull();
    expect(descriptionHeadingLevel("1. Крутящий момент")).toBe(3);
    expect(descriptionHeadingLevel("Класс защиты")).toBe(3);
    expect(descriptionHeadingLevel("Температурный режим")).toBe(3);
    expect(descriptionHeadingLevel("✅ Преимущества серии")).toBe(2);

    const blocks = parseProductDescription(
      [
        "Приводы серии DA..FU предназначены для клапанов.",
        "",
        "Ключевые характеристики:",
        "",
        "1. Крутящий момент",
        "",
        "– Доступны модели с моментом: 3, 5, 10 Нм",
        "",
        "Например:",
        "",
        "– DA10FU230-DS подходит для заслонок до 1 м²",
        "",
        "2. Напряжение питания",
        "",
        "– Работает от AC 100…240 В",
        "",
        "Области применения",
        "",
        "– Регулирование воздушных потоков",
      ].join("\n"),
    );

    expect(blocks).toEqual([
      {
        type: "paragraph",
        text: "Приводы серии DA..FU предназначены для клапанов.",
      },
      { type: "section", title: "Ключевые характеристики", level: 2 },
      { type: "section", title: "1. Крутящий момент", level: 3 },
      {
        type: "list",
        items: ["Доступны модели с моментом: 3, 5, 10 Нм"],
      },
      { type: "paragraph", text: "Например" },
      {
        type: "list",
        items: ["DA10FU230-DS подходит для заслонок до 1 м²"],
      },
      { type: "section", title: "2. Напряжение питания", level: 3 },
      { type: "list", items: ["Работает от AC 100…240 В"] },
      { type: "section", title: "Области применения", level: 2 },
      { type: "list", items: ["Регулирование воздушных потоков"] },
    ]);
  });

  it("promotes bare SA application subheads and demotes instruction lead-ins", () => {
    const desc = parseProductDescription(
      [
        "Области применения",
        "",
        "Промышленные объекты:",
        "",
        "– Цеха",
        "",
        "Общественные здания",
        "",
        "– ТЦ",
        "",
        "Специальные сооружения",
        "",
        "– Шахты",
        "",
        "Интеграция",
        "",
        "– Пульты",
      ].join("\n"),
    );
    expect(desc.filter((b) => b.type === "section")).toEqual([
      { type: "section", title: "Области применения", level: 2 },
      { type: "section", title: "Промышленные объекты", level: 3 },
      { type: "section", title: "Общественные здания", level: 3 },
      { type: "section", title: "Специальные сооружения", level: 3 },
      { type: "section", title: "Интеграция", level: 3 },
    ]);

    const inst = parseInstructions(
      [
        "9. Хранение:",
        "",
        "– Температура: -30...+80 °C",
        "",
        "Привод предназначен для использования в:",
        "",
        "– Метро",
      ].join("\n"),
    );
    expect(inst).toContainEqual({
      type: "paragraph",
      text: "Привод предназначен для использования в",
    });
    expect(
      inst.some(
        (b) =>
          b.type === "section" &&
          b.title.toLowerCase().includes("предназначен"),
      ),
    ).toBe(false);
  });

  it("drops empty bare subheads with no body", () => {
    const blocks = parseProductDescription(
      [
        "Эксплуатационные параметры",
        "",
        "Класс защиты:",
        "",
        "– II для 230 В",
        "",
        "Температурный режим",
        "",
        "Уровень шума:",
        "",
        "– двигатель: до 45 дБ",
      ].join("\n"),
    );
    expect(blocks.map((b) => (b.type === "section" ? b.title : b.type))).toEqual([
      "Эксплуатационные параметры",
      "Класс защиты",
      "list",
      "Уровень шума",
      "list",
    ]);
  });
});
