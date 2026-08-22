import { describe, expect, it } from "vitest";

import {
  locationHashMatches,
  scrollGateSatisfied,
} from "./deferredMountGates";

describe("deferredMountGates", () => {
  it("matches hash ids without the leading hash", () => {
    expect(locationHashMatches(["podbor"], "#podbor")).toBe(true);
    expect(locationHashMatches(["podbor"], "podbor")).toBe(true);
    expect(locationHashMatches(["podbor"], "#catalog")).toBe(false);
  });

  it("opens scroll gate after scroll or hash hit", () => {
    expect(scrollGateSatisfied(1, false, false)).toBe(false);
    expect(scrollGateSatisfied(1, true, false)).toBe(true);
    expect(scrollGateSatisfied(1, false, true)).toBe(true);
    expect(scrollGateSatisfied(undefined, false, false)).toBe(true);
  });
});
