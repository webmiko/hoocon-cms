import { describe, expect, it } from "vitest";

import { stockAvailabilityLabel } from "./stockAvailability";

describe("stockAvailabilityLabel", () => {
  it("labels on-hand vs made-to-order", () => {
    expect(stockAvailabilityLabel(true)).toBe("Есть в наличии");
    expect(stockAvailabilityLabel(false)).toBe("Под заказ");
    expect(stockAvailabilityLabel(undefined)).toBe("Под заказ");
  });
});
