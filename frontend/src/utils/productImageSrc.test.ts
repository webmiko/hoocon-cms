import { describe, expect, it } from "vitest";

import {
  productCardImageSrc,
  productFullImageSrc,
} from "./productImageSrc";

describe("productImageSrc", () => {
  it("prefers image_card for tiles", () => {
    expect(
      productCardImageSrc({
        image: "/media/full.webp",
        image_card: "/media/card.webp",
      }),
    ).toBe("/media/card.webp");
  });

  it("falls back to full image when card is missing", () => {
    expect(productCardImageSrc({ image: "/media/full.webp" })).toBe(
      "/media/full.webp",
    );
    expect(
      productCardImageSrc({ image: "/media/full.webp", image_card: "" }),
    ).toBe("/media/full.webp");
  });

  it("keeps full URL for PDP", () => {
    expect(
      productFullImageSrc({
        image: "/media/full.webp",
        image_card: "/media/card.webp",
      }),
    ).toBe("/media/full.webp");
  });
});
