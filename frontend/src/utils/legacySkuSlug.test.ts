import { describe, expect, it } from "vitest";

import { shouldResolveLegacySkuSlug } from "./legacySkuSlug";

describe("shouldResolveLegacySkuSlug", () => {
  it("accepts hyphenated catalog SKU slugs", () => {
    expect(shouldResolveLegacySkuSlug("privod-vozdushniy-hva-5nm-s")).toBe(
      true,
    );
  });

  it("rejects short or reserved paths before SKU API", () => {
    expect(shouldResolveLegacySkuSlug("about")).toBe(false);
    expect(shouldResolveLegacySkuSlug("api")).toBe(false);
  });
});
