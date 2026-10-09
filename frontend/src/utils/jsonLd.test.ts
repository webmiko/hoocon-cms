import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { buildProductJsonLd } from "./jsonLd";

const here = dirname(fileURLToPath(import.meta.url));
const skuPage = readFileSync(join(here, "..", "pages", "SkuDetailPage.tsx"), "utf8");

const base = { name: "DA24-10", slug: "da24-10", category_slug: "privody" };

describe("buildProductJsonLd offers", () => {
  it("omits offers without a price (Offer without price is invalid for rich results)", () => {
    expect(buildProductJsonLd({ ...base, price: null })).not.toHaveProperty("offers");
    expect(buildProductJsonLd({ ...base, price: "1000", price_on_request: true })).not.toHaveProperty("offers");
  });

  it("marks availability from in_stock instead of always InStock", () => {
    const onHand = buildProductJsonLd({ ...base, price: "1000", in_stock: true }).offers as Record<string, string>;
    const toOrder = buildProductJsonLd({ ...base, price: "1000", in_stock: false }).offers as Record<string, string>;
    const unknown = buildProductJsonLd({ ...base, price: "1000" }).offers as Record<string, string>;
    expect(onHand).toMatchObject({ price: "1000", priceCurrency: "RUB", availability: "https://schema.org/InStock" });
    expect(toOrder.availability).toBe("https://schema.org/PreOrder");
    expect(unknown.availability).toBe("https://schema.org/PreOrder");
  });

  it("PDP passes the displayed variant stock into JSON-LD", () => {
    expect(skuPage).toMatch(/buildProductJsonLd\(\{[\s\S]*?in_stock: Boolean\(displayInStock\)/);
  });
});
