import { describe, expect, it } from "vitest";

import {
  buildHighlightPattern,
  escapeRegExp,
  highlightQuerySegments,
} from "./highlightQuery";

describe("escapeRegExp", () => {
  it("escapes metacharacters", () => {
    expect(escapeRegExp("a+b(c)")).toBe("a\\+b\\(c\\)");
  });
});

describe("buildHighlightPattern", () => {
  it("returns null for blank query", () => {
    expect(buildHighlightPattern("")).toBeNull();
    expect(buildHighlightPattern("   ")).toBeNull();
  });

  it("matches phrase case-insensitively", () => {
    const pattern = buildHighlightPattern("DA2MU");
    expect(pattern).not.toBeNull();
    expect("Привод da2mu 2 Нм".match(pattern!)).toEqual(
      expect.arrayContaining([expect.stringMatching(/da2mu/i)]),
    );
  });
});

describe("highlightQuerySegments", () => {
  it("returns plain text when query is empty", () => {
    expect(highlightQuerySegments("Электропривод DA2MU", "")).toEqual([
      { text: "Электропривод DA2MU", match: false },
    ]);
  });

  it("highlights a single word", () => {
    expect(highlightQuerySegments("Электропривод DA2MU 2 Нм", "DA2MU")).toEqual([
      { text: "Электропривод ", match: false },
      { text: "DA2MU", match: true },
      { text: " 2 Нм", match: false },
    ]);
  });

  it("highlights a multi-word phrase when present", () => {
    const text = "Управляющий сигнал Y и обратная связь";
    expect(highlightQuerySegments(text, "сигнал Y")).toEqual([
      { text: "Управляющий ", match: false },
      { text: "сигнал Y", match: true },
      { text: " и обратная связь", match: false },
    ]);
  });

  it("highlights separate tokens when phrase is split", () => {
    const segments = highlightQuerySegments(
      "Крутящий момент 2 Нм, напряжение 230 В",
      "момент 230",
    );
    const matched = segments.filter((s) => s.match).map((s) => s.text);
    expect(matched).toEqual(expect.arrayContaining(["момент", "230"]));
  });

  it("is case-insensitive for Cyrillic", () => {
    expect(highlightQuerySegments("воздушный привод", "Воздушный")).toEqual([
      { text: "воздушный", match: true },
      { text: " привод", match: false },
    ]);
  });
});
