import { describe, expect, it } from "vitest";

import { extractArticleToc } from "./articleToc";

describe("extractArticleToc", () => {
  it("injects stable ids on h2 headings for TOC hrefs", () => {
    const raw = [
      "<h2>Как читать линейку</h2>",
      "<p>текст</p>",
      "<h2>С пружинным возвратом (FU)</h2>",
      "<p>ещё</p>",
      "<h2>Клапаны дымоудаления (SA MU)</h2>",
    ].join("");
    const { html, items } = extractArticleToc(raw);
    expect(items.length).toBe(3);
    for (const item of items) {
      expect(html).toContain(`id="${item.id}"`);
      expect(item.id.length).toBeGreaterThan(0);
    }
  });
});
