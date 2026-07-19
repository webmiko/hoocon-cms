import { describe, expect, it } from "vitest";

import { specDisplayUnit } from "./specDisplay";

describe("specDisplayUnit", () => {
  it("omits с when value already has с or сек", () => {
    expect(specDisplayUnit("≤ 100 с", "с")).toBe("");
    expect(specDisplayUnit("≤ 100 сек", "с")).toBe("");
    expect(specDisplayUnit("≤ 30 секунд (90°)", "с")).toBe("");
  });

  it("keeps unit when value is bare number", () => {
    expect(specDisplayUnit("100", "с")).toBe("с");
    expect(specDisplayUnit("5", "Нм")).toBe("Нм");
  });
});
