import { describe, expect, it } from "vitest";

import { countVisibleNavItems } from "../utils/navOverflow";

describe("countVisibleNavItems", () => {
  const widths = [60, 55, 70, 90, 95, 85, 75];
  const more = 48;

  it("shows all when there is enough room", () => {
    expect(countVisibleNavItems(700, widths, more)).toBe(7);
  });

  it("hides trailing items into Ещё when tight", () => {
    const visible = countVisibleNavItems(320, widths, more);
    expect(visible).toBeGreaterThan(0);
    expect(visible).toBeLessThan(7);
  });

  it("returns 0 for empty / zero width", () => {
    expect(countVisibleNavItems(0, widths, more)).toBe(0);
    expect(countVisibleNavItems(200, [], more)).toBe(0);
  });
});
