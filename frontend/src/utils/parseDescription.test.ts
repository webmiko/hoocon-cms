import { describe, expect, it } from "vitest";

import { parseDescription } from "./parseDescription";

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
});
