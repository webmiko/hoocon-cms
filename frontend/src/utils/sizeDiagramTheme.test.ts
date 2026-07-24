import { describe, expect, it } from "vitest";

import {
  isSizeDiagram,
  isTechnicalDiagram,
  sizeDiagramSrcForTheme,
} from "./sizeDiagramTheme";

describe("sizeDiagramSrcForTheme", () => {
  const light = "/media/product_images/148/abc_8100-bv215a-size.webp";
  const dark = "/media/product_images/148/abc_8100-bv215a-size-dark.webp";

  it("detects size diagrams", () => {
    expect(isSizeDiagram(light)).toBe(true);
    expect(isSizeDiagram(dark)).toBe(true);
    expect(isSizeDiagram("/media/x-0.webp", "product")).toBe(false);
  });

  it("detects manual wiring and dimensions crops", () => {
    expect(
      isTechnicalDiagram(
        "/media/x_da5fu24-d-wiring.webp",
        "DA5FU | Схема подключения из инструкции",
      ),
    ).toBe(true);
    expect(
      isTechnicalDiagram(
        "/media/x_da5fu24-d-dimensions.webp",
        "DA5FU | Габаритные размеры привода (мм)",
      ),
    ).toBe(true);
    expect(
      isTechnicalDiagram(
        "/media/x_h8101-aux_switch.webp",
        "H8101 | Вспомогательные концевые выключатели",
      ),
    ).toBe(true);
    expect(
      isTechnicalDiagram(
        "/media/x_h8101-settings.webp",
        "H8101 | Настройка DIP-переключателей",
      ),
    ).toBe(true);
    expect(isTechnicalDiagram("/media/x-0.webp", "product photo")).toBe(false);
  });

  it("swaps to white-line clone in dark theme", () => {
    expect(sizeDiagramSrcForTheme(light, "dark")).toBe(dark);
    expect(sizeDiagramSrcForTheme(dark, "dark")).toBe(dark);
  });

  it("keeps or restores black-line asset in light theme", () => {
    expect(sizeDiagramSrcForTheme(light, "light")).toBe(light);
    expect(sizeDiagramSrcForTheme(dark, "light")).toBe(light);
  });

  it("leaves product photos and PDF crops unchanged by theme swap", () => {
    const product = "/media/product_images/148/abc_8100-bv215a-0.webp";
    const wiring = "/media/product_images/37/x_da5fu24-d-wiring.webp";
    expect(sizeDiagramSrcForTheme(product, "dark")).toBe(product);
    expect(sizeDiagramSrcForTheme(product, "light")).toBe(product);
    expect(sizeDiagramSrcForTheme(wiring, "dark")).toBe(wiring);
  });
});
