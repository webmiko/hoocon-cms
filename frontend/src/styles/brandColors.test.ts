import { describe, expect, it } from "vitest";

import {
  COLOR_BG,
  COLOR_BRAND,
  COLOR_BRAND_HOVER,
  COLOR_ON_BRAND,
} from "./brandColors";

describe("brandColors", () => {
  it("matches light-theme tokens used by PWA manifest and CSS", () => {
    expect(COLOR_BRAND).toBe("#da0e2b");
    expect(COLOR_BRAND_HOVER).toBe("#b80c24");
    expect(COLOR_ON_BRAND).toBe("#ffffff");
    expect(COLOR_BG).toBe("#f3f4f7");
  });
});
