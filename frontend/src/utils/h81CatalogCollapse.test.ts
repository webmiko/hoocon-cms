import { describe, expect, it } from "vitest";

import { collapseH81CatalogSkus } from "./h81CatalogCollapse";
import {
  applyVariantPatch,
  resolveSiblingSlug,
  selectionFromSibling,
  type SiblingEdition,
} from "./skuVariantResolve";

describe("collapseH81CatalogSkus", () => {
  it("keeps one row per H81 family product_slug", () => {
    const rows = [
      { slug: "a", product_slug: "h8101" },
      { slug: "b", product_slug: "h8101" },
      { slug: "c", product_slug: "h8102" },
      { slug: "d", product_slug: "da5fu" },
    ];
    const out = collapseH81CatalogSkus(rows);
    expect(out.map((r) => r.slug)).toEqual(["a", "c", "d"]);
  });

  it("keeps one row per brass 8100-bv DN product_slug", () => {
    const rows = [
      { slug: "a", product_slug: "8100-bv215" },
      { slug: "b", product_slug: "8100-bv215" },
      { slug: "c", product_slug: "8100-bv220" },
      { slug: "d", product_slug: "da5fu" },
    ];
    const out = collapseH81CatalogSkus(rows);
    expect(out.map((r) => r.slug)).toEqual(["a", "c", "d"]);
  });

  it("keeps one row per DAMU / SAMU / SAFU / HVA / HVD product_slug", () => {
    const rows = [
      { slug: "da-a", product_slug: "privod-vozdushniy-bez-pruzhini-damu-8nm" },
      { slug: "da-b", product_slug: "privod-vozdushniy-bez-pruzhini-damu-8nm" },
      { slug: "sa-a", product_slug: "privod-dimoudaleniya-10nm" },
      { slug: "sa-b", product_slug: "privod-dimoudaleniya-10nm" },
      { slug: "safu-a", product_slug: "privod-protivopozharniy-3nm" },
      { slug: "safu-b", product_slug: "privod-protivopozharniy-3nm" },
      { slug: "hva-a", product_slug: "privod-vozdushniy-hva-5nm" },
      { slug: "hva-b", product_slug: "privod-vozdushniy-hva-5nm" },
      { slug: "hvd-a", product_slug: "privod-dimoudaleniya-hvd-3f" },
      { slug: "hvd-b", product_slug: "privod-dimoudaleniya-hvd-3f" },
      { slug: "hvd-air", product_slug: "privod-vozdushniy-hvd-40q" },
      { slug: "other", product_slug: "da5fu" },
    ];
    const out = collapseH81CatalogSkus(rows);
    expect(out.map((r) => r.slug)).toEqual([
      "da-a",
      "sa-a",
      "safu-a",
      "hva-a",
      "hvd-a",
      "hvd-air",
      "other",
    ]);
  });
});

describe("resolveSiblingSlug", () => {
  const siblings: SiblingEdition[] = [
    {
      slug: "s-a",
      sku_code: "H8101-BV215A-24A",
      body: "BV215A",
      dn: "15",
      ways: "2-ходовый",
      kvs: "1,6",
      voltage: "24",
      control: "A",
      aux_switch: false,
      in_stock: true,
    },
    {
      slug: "s-as",
      sku_code: "H8101-BV215A-24AS",
      body: "BV215A",
      dn: "15",
      ways: "2-ходовый",
      kvs: "1,6",
      voltage: "24",
      control: "AS",
      aux_switch: true,
      in_stock: true,
    },
    {
      slug: "s-b",
      sku_code: "H8101-BV215B-24A",
      body: "BV215B",
      dn: "15",
      ways: "2-ходовый",
      kvs: "2,5",
      voltage: "24",
      control: "A",
      aux_switch: false,
      in_stock: false,
    },
    {
      slug: "s-40",
      sku_code: "H8101-BV340B-24DS",
      body: "BV340B",
      dn: "40",
      ways: "3-ходовый",
      kvs: "40",
      voltage: "24",
      control: "DS",
      aux_switch: true,
      in_stock: false,
    },
    {
      slug: "s-50",
      sku_code: "H8101-BV350A-24A",
      body: "BV350A",
      dn: "50",
      ways: "3-ходовый",
      kvs: "40",
      voltage: "24",
      control: "A",
      aux_switch: false,
      in_stock: true,
    },
  ];

  it("resolves voltage+control+body", () => {
    const sel = selectionFromSibling(siblings[0]);
    sel.control = "AS";
    expect(resolveSiblingSlug(siblings, sel, { control: "AS" })).toBe("s-as");
  });

  it("resolves kvs change to matching body", () => {
    const sel = selectionFromSibling(siblings[0]);
    const match = applyVariantPatch(siblings, sel, { kvs: "2,5" });
    expect(match?.slug).toBe("s-b");
    expect(match?.body).toBe("BV215B");
  });

  it("coerces DN change when old Kvs is unavailable", () => {
    const with315: SiblingEdition[] = [
      ...siblings,
      {
        slug: "s-315",
        sku_code: "H8101-BV315A-24DS",
        body: "BV315A",
        dn: "15",
        ways: "3-ходовый",
        kvs: "1,6",
        voltage: "24",
        control: "DS",
        aux_switch: true,
        in_stock: true,
      },
    ];
    const sel = selectionFromSibling(siblings[3]); // DN40 Kvs40 3-way DS
    const match = applyVariantPatch(with315, sel, { dn: "15" });
    expect(match?.slug).toBe("s-315");
    expect(match?.ways).toBe("3-ходовый");
    expect(match?.kvs).toBe("1,6");
    expect(match?.control).toBe("DS");
  });

  it("keeps ways when changing DN within same ways", () => {
    const sel = selectionFromSibling(siblings[3]);
    const match = applyVariantPatch(siblings, sel, { dn: "50" });
    expect(match?.slug).toBe("s-50");
    expect(match?.ways).toBe("3-ходовый");
    expect(match?.control).toBe("A");
  });

  it("keeps DN when switching ways if that DN exists", () => {
    const sel = selectionFromSibling(siblings[3]); // DN40 3-way
    const with240: SiblingEdition[] = [
      ...siblings,
      {
        slug: "s-240",
        sku_code: "H8101-BV240B-24DS",
        body: "BV240B",
        dn: "40",
        ways: "2-ходовый",
        kvs: "40",
        voltage: "24",
        control: "DS",
        aux_switch: true,
        in_stock: true,
      },
    ];
    const match = applyVariantPatch(with240, sel, { ways: "2-ходовый" });
    expect(match?.slug).toBe("s-240");
    expect(match?.dn).toBe("40");
    expect(match?.ways).toBe("2-ходовый");
  });
});
