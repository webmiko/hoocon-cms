import { describe, expect, it } from "vitest";

import { softBreak, softBreakParts } from "./softBreak";

describe("softBreak", () => {
  it("keeps factory-setting note as one nowrap part", () => {
    const raw =
      "0(2)...10 В= / 0(4)...20 мА (Заводская установка 0...10 В=)";
    const parts = softBreakParts(raw);
    const nowrap = parts.filter((p) => p.nowrap);
    expect(nowrap).toHaveLength(1);
    expect(nowrap[0]?.text).toBe("(Заводская установка 0...10 В=)");
    // Soft break immediately before the note.
    const idx = parts.findIndex((p) => p.nowrap);
    expect(parts[idx - 1]?.text).toBe("\u200B");
  });

  it("keeps edition suffix as one nowrap part", () => {
    const parts = softBreakParts("DA4MU24 (−D/−DS/−A/−AS)");
    const nowrap = parts.filter((p) => p.nowrap);
    expect(nowrap).toHaveLength(1);
    expect(nowrap[0]?.text).toContain("−D/−DS/−A/−AS");
  });

  it("uses NBSP inside nowrap for plain-string softBreak", () => {
    const out = softBreak("x (Заводская установка 0...10 В=)");
    expect(out.includes("Заводская\u00A0установка")).toBe(true);
    expect(out.replaceAll("\u00A0", " ").replaceAll("\u200B", "").replaceAll("\u2060", "")).toBe(
      "x (Заводская установка 0...10 В=)",
    );
  });

  it("does not soft-break after opening parenthesis", () => {
    const out = softBreak(
      "Электрический шаровой кран 2-ходовый DN 25 H8101-BV225A (стандартная серия) для HVAC.",
    );
    expect(out.includes("(\u200B")).toBe(false);
    expect(out.includes("(\u2060") || out.includes("(стандартная")).toBe(true);
    // Short parenthetical stays one nowrap token (NBSP between words).
    expect(out.includes("стандартная\u00A0серия")).toBe(true);
  });

  it("lets long material notes wrap inside narrow ТТХ cards", () => {
    const raw = "Ковкий чугун (с шаровидным графитом)";
    const parts = softBreakParts(raw);
    expect(parts.some((p) => p.nowrap && p.text.includes("шаровидным"))).toBe(
      false,
    );
    const joined = softBreak(raw);
    // Spaces stay breakable (no NBSP lock on the long note).
    expect(joined.includes("шаровидным\u00A0графитом")).toBe(false);
    expect(joined.replaceAll("\u200B", "").replaceAll("\u2060", "")).toBe(raw);
  });

  it("lets long factory-setting instruction notes wrap", () => {
    const raw =
      "DIP-переключатели режима сигнала (заводская установка: вход 0…10 В=, обратная связь 0…10 В=):";
    const parts = softBreakParts(raw);
    expect(
      parts.some((p) => p.nowrap && p.text.includes("обратная связь")),
    ).toBe(false);
    const joined = softBreak(raw);
    expect(joined.includes("вход\u00A0")).toBe(false);
  });
});
