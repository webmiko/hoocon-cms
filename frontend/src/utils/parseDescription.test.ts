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
});
