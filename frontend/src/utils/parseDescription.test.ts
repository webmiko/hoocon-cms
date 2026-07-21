import { describe, expect, it } from "vitest";

import {
  instructionHeadingLevel,
  parseDescription,
  parseInstructions,
} from "./parseDescription";

describe("parseDescription", () => {
  it("treats bare section titles without colon as headings", () => {
    const blocks = parseDescription(
      [
        "Электропривод HVD представляет собой надежное устройство.",
        "",
        "Области применения",
        "",
        "– Системы вентиляции",
        "",
        "Преимущества",
        "",
        "– Высокая надежность конструкции",
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
        "– Надежность конструкции",
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

  it("assigns h2/h3/h4 levels for install instruction headings", () => {
    expect(instructionHeadingLevel("ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ")).toBe(2);
    expect(instructionHeadingLevel("1. ПОДГОТОВКА К МОНТАЖУ")).toBe(3);
    expect(instructionHeadingLevel("2. ТРЕБОВАНИЯ К МОНТАЖУ")).toBe(3);
    expect(instructionHeadingLevel("3.1 Монтаж на заслонку")).toBe(4);
    expect(instructionHeadingLevel("7.2 Требуется")).toBe(4);
    expect(instructionHeadingLevel("– Пункт списка")).toBeNull();
  });

  it("reclassifies numbered instruction chapters from paragraphs to sections", () => {
    const blocks = parseInstructions(
      [
        "ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ",
        "",
        "1. ПОДГОТОВКА К МОНТАЖУ",
        "",
        "– Проверьте комплектацию",
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
      { type: "section", title: "ИНСТРУКЦИЯ ПО УСТАНОВКЕ И УПРАВЛЕНИЮ", level: 2 },
      { type: "section", title: "1. ПОДГОТОВКА К МОНТАЖУ", level: 3 },
      { type: "list", items: ["Проверьте комплектацию"] },
      { type: "section", title: "2. ТРЕБОВАНИЯ К МОНТАЖУ", level: 3 },
      { type: "section", title: "3. ЭТАПЫ УСТАНОВКИ", level: 3 },
      { type: "section", title: "3.1 Монтаж на заслонку", level: 4 },
      { type: "list", items: ["Закрепите привод"] },
    ]);
  });
});
