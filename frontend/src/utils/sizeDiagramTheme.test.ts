import { describe, expect, it } from "vitest";

import { isSizeDiagram, sizeDiagramSrcForTheme } from "./sizeDiagramTheme";

describe("sizeDiagramSrcForTheme", () => {
  const light =
    "/media/product_images/148/abc_8100-bv215a-size.webp";
  const dark =
    "/media/product_images/148/abc_8100-bv215a-size-dark.webp";

  it("detects size diagrams", () => {
    expect(isSizeDiagram(light)).toBe(true);
    expect(isSizeDiagram(dark)).toBe(true);
    expect(isSizeDiagram(light, "8100-bv215a габариты")).toBe(true);
    expect(isSizeDiagram("/media/x-0.webp", "product")).toBe(false);
  });

  it("swaps to white-line clone in dark theme", () => {
    expect(sizeDiagramSrcForTheme(light, "dark")).toBe(dark);
    expect(sizeDiagramSrcForTheme(dark, "dark")).toBe(dark);
  });

  it("keeps or restores black-line asset in light theme", () => {
    expect(sizeDiagramSrcForTheme(light, "light")).toBe(light);
    expect(sizeDiagramSrcForTheme(dark, "light")).toBe(light);
  });

  it("leaves product photos unchanged", () => {
    const product = "/media/product_images/148/abc_8100-bv215a-0.webp";
    expect(sizeDiagramSrcForTheme(product, "dark")).toBe(product);
    expect(sizeDiagramSrcForTheme(product, "light")).toBe(product);
  });
});
