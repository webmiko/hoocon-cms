import { describe, expect, it } from "vitest";

import {
  absoluteOgImageUrl,
  catalogListingSeoTitle,
  categorySeoDescription,
  metaDescription,
  skuNotFoundSeoTitle,
} from "./seoMeta";

describe("metaDescription", () => {
  it("truncates at a word boundary under the cap", () => {
    const long =
      "Электроприводы для вентиляции и кондиционирования с паспортами PDF "
      + "и подбором аналогов Belimo для проектных спецификаций инженеров ОВК.";
    const out = metaDescription(long, 80);
    expect(out.endsWith("…")).toBe(true);
    expect(out.length).toBeLessThanOrEqual(80);
    expect(out.includes("спецификаций")).toBe(false);
  });
});

describe("categorySeoDescription", () => {
  it("prefers category body over shared catalog fallback", () => {
    expect(
      categorySeoDescription(
        "Приводы ОЗК",
        "Электроприводы для огнезадерживающих клапанов серии SA.",
      ),
    ).toContain("огнезадерживающих");
  });

  it("falls back to catalog blurb when empty", () => {
    expect(categorySeoDescription("", "")).toContain("Каталог электроприводов");
  });
});

describe("catalogListingSeoTitle", () => {
  it("uses category name when available", () => {
    expect(catalogListingSeoTitle("sharovye-krany", "Шаровые краны")).toBe(
      "Шаровые краны",
    );
  });

  it("falls back to slug-specific title instead of root catalog", () => {
    expect(catalogListingSeoTitle("sharovye-krany")).toBe(
      "Каталог — sharovye-krany",
    );
  });

  it("uses root title only for /catalog", () => {
    expect(catalogListingSeoTitle()).toContain("Каталог электроприводов");
  });
});

describe("skuNotFoundSeoTitle", () => {
  it("includes slug for unique 404 titles", () => {
    expect(skuNotFoundSeoTitle("h8102-h8102-bv215c-24ds")).toContain(
      "h8102-h8102-bv215c-24ds",
    );
  });
});

describe("absoluteOgImageUrl", () => {
  it("prefixes relative media paths", () => {
    expect(absoluteOgImageUrl("/media/a.webp")).toBe(
      "https://hoocon.ru/media/a.webp",
    );
  });

  it("keeps absolute URLs", () => {
    expect(absoluteOgImageUrl("https://cdn.example/x.jpg")).toBe(
      "https://cdn.example/x.jpg",
    );
  });

  it("returns undefined for empty", () => {
    expect(absoluteOgImageUrl(null)).toBeUndefined();
    expect(absoluteOgImageUrl("  ")).toBeUndefined();
  });
});
