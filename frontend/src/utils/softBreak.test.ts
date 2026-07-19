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
    expect(out.replaceAll("\u00A0", " ").replaceAll("\u200B", "")).toBe(
      "x (Заводская установка 0...10 В=)",
    );
  });
});
