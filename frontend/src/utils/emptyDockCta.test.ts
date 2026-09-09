import { describe, expect, it } from "vitest";

import { emptyDockCtaForPath, isCatalogRoute } from "./emptyDockCta";

describe("isCatalogRoute", () => {
  it("matches /catalog and nested paths only", () => {
    expect(isCatalogRoute("/catalog")).toBe(true);
    expect(isCatalogRoute("/catalog/")).toBe(true);
    expect(isCatalogRoute("/catalog/adaptery")).toBe(true);
    expect(isCatalogRoute("/catalog/adaptery/sku-1")).toBe(true);
    expect(isCatalogRoute("/")).toBe(false);
    expect(isCatalogRoute("/consultation")).toBe(false);
    expect(isCatalogRoute("/gde-kupit")).toBe(false);
    expect(isCatalogRoute("/catalogs")).toBe(false);
  });
});

describe("emptyDockCtaForPath", () => {
  it("keeps KP CTA on catalog pages", () => {
    expect(emptyDockCtaForPath("/catalog")).toEqual({
      kind: "to",
      to: "/consultation",
      label: "Запросить КП",
      shortLabel: "КП",
    });
    expect(emptyDockCtaForPath("/catalog/adaptery/x")).toMatchObject({
      to: "/consultation",
      label: "Запросить КП",
    });
  });

  it("sends non-catalog pages to the catalog", () => {
    expect(emptyDockCtaForPath("/")).toEqual({
      kind: "to",
      to: "/catalog",
      label: "В каталог",
      shortLabel: "Каталог",
    });
    expect(emptyDockCtaForPath("/gde-kupit")).toMatchObject({
      to: "/catalog",
      label: "В каталог",
    });
  });

  it("keeps OEM mailto on /zavod", () => {
    expect(emptyDockCtaForPath("/zavod").kind).toBe("href");
    expect(emptyDockCtaForPath("/zavod/")).toMatchObject({
      kind: "href",
      shortLabel: "OEM",
    });
  });
});
