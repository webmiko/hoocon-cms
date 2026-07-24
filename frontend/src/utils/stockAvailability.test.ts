import { describe, expect, it } from "vitest";

import { stockAvailabilityLabel } from "./stockAvailability";

describe("stockAvailabilityLabel", () => {
  it("labels in-stock and out-of-stock", () => {
    expect(stockAvailabilityLabel(true)).toBe("Есть в наличии");
    expect(stockAvailabilityLabel(false)).toBe("Нет в наличии");
    expect(stockAvailabilityLabel(undefined)).toBe("Нет в наличии");
  });
});
