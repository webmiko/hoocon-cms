import { describe, expect, it } from "vitest";

import {
  HOOCON_SPLASH_MIN_MS,
  HOOCON_SPLASH_MOBILE_MQ,
  splashRemainingDwellMs,
} from "./hooconMainCss";

describe("splashRemainingDwellMs", () => {
  it("waits the full min when content is ready immediately", () => {
    expect(splashRemainingDwellMs(0)).toBe(HOOCON_SPLASH_MIN_MS);
    expect(splashRemainingDwellMs(100)).toBe(HOOCON_SPLASH_MIN_MS - 100);
  });

  it("returns 0 when load already exceeded the minimum", () => {
    expect(splashRemainingDwellMs(HOOCON_SPLASH_MIN_MS)).toBe(0);
    expect(splashRemainingDwellMs(HOOCON_SPLASH_MIN_MS + 500)).toBe(0);
  });

  it("treats invalid elapsed as full min dwell", () => {
    expect(splashRemainingDwellMs(Number.NaN)).toBe(HOOCON_SPLASH_MIN_MS);
    expect(splashRemainingDwellMs(-10)).toBe(HOOCON_SPLASH_MIN_MS);
  });
});

describe("HOOCON_SPLASH_MOBILE_MQ", () => {
  it("matches the mobile layout breakpoint (≤960px)", () => {
    expect(HOOCON_SPLASH_MOBILE_MQ).toBe("(max-width: 960px)");
  });
});
