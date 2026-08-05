import { describe, expect, it } from "vitest";

import {
  catalogCategoryPath,
  catalogPathForSku,
  catalogSkuPath,
} from "./catalogPaths";

describe("catalogPaths", () => {
  it("builds nested category and sku paths", () => {
    expect(catalogCategoryPath("adaptery")).toBe("/catalog/adaptery");
    expect(catalogSkuPath("adaptery", "adapter-br-m")).toBe(
      "/catalog/adaptery/adapter-br-m",
    );
    expect(
      catalogPathForSku({
        category_slug: "adaptery",
        slug: "adapter-br-ml",
      }),
    ).toBe("/catalog/adaptery/adapter-br-ml");
  });

  it("strips duplicated catalog/category prefixes", () => {
    expect(catalogCategoryPath("/catalog/adaptery")).toBe("/catalog/adaptery");
    expect(catalogSkuPath("/catalog/adaptery", "adapter-br-m")).toBe(
      "/catalog/adaptery/adapter-br-m",
    );
    expect(catalogSkuPath("adaptery", "adaptery/adapter-br-m")).toBe(
      "/catalog/adaptery/adapter-br-m",
    );
    expect(
      catalogSkuPath("adaptery", "/catalog/adaptery/adapter-br-ml"),
    ).toBe("/catalog/adaptery/adapter-br-ml");
  });
});
