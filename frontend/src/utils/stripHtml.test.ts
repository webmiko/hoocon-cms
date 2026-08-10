import { describe, expect, it } from "vitest";

import { stripHtmlToText } from "./stripHtml";

describe("stripHtmlToText", () => {
  it("strips tags and decodes &nbsp;", () => {
    const html =
      "<p>Привод <strong>HVA-5NM</strong> с моментом 5&nbsp;Н·м.</p>";
    expect(stripHtmlToText(html)).toBe("Привод HVA-5NM с моментом 5 Н·м.");
  });

  it("decodes numeric and hex entities", () => {
    expect(stripHtmlToText("5&#160;Н·м")).toBe("5 Н·м");
    expect(stripHtmlToText("A&#x2014;B")).toBe("A—B");
  });

  it("returns empty for blank input", () => {
    expect(stripHtmlToText("")).toBe("");
    expect(stripHtmlToText("   ")).toBe("");
  });
});
