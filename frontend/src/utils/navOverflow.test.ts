import { describe, expect, it } from "vitest";

import { countVisibleNavItems, DESKTOP_NAV_ITEMS } from "../utils/navOverflow";

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

describe("DESKTOP_NAV_ITEMS", () => {
  it("puts documentation in the main menu, next to the catalog", () => {
    expect(DESKTOP_NAV_ITEMS[0]).toEqual({ to: "/catalog", label: "Каталог" });
    expect(DESKTOP_NAV_ITEMS[1]).toEqual({
      to: "/dokumentaciya",
      label: "Документация",
    });
  });
});
