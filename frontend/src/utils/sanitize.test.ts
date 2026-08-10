import { describe, expect, it } from "vitest";

import { downgradeCmsH1, sanitizeHtml } from "./sanitize";

describe("downgradeCmsH1", () => {
  it("rewrites h1 to h2 keeping attributes", () => {
    expect(downgradeCmsH1('<h1 id="x" class="t">Title</h1>')).toBe(
      '<h2 id="x" class="t">Title</h2>',
    );
  });
});

describe("sanitizeHtml", () => {
  it("does not leave h1 in sanitized output", () => {
    const out = sanitizeHtml("<h1>From CMS</h1><p>Body</p>");
    expect(out.toLowerCase()).not.toContain("<h1");
    expect(out.toLowerCase()).toContain("<h2");
    expect(out).toContain("From CMS");
  });
});
