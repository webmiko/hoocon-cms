import { describe, expect, it } from "vitest";

import { navPathDepth, navSlideDirection } from "./navSlide";

describe("navPathDepth", () => {
  it("ranks catalog list → category → SKU", () => {
    expect(navPathDepth("/catalog")).toBe(1);
    expect(navPathDepth("/catalog/privody")).toBe(2);
    expect(navPathDepth("/catalog/privody/da24")).toBe(3);
  });
});

describe("navSlideDirection", () => {
  it("slides up into PDP and down back to category", () => {
    expect(
      navSlideDirection("/catalog/privody", "/catalog/privody/da24"),
    ).toBe("up");
    expect(
      navSlideDirection("/catalog/privody/da24", "/catalog/privody"),
    ).toBe("down");
  });

  it("returns none for same depth or identical paths", () => {
    expect(navSlideDirection("/catalog/a", "/catalog/b")).toBe("none");
    expect(navSlideDirection("/catalog/a/x", "/catalog/a/x")).toBe("none");
  });
});
