import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import { CompatiblePositions } from "./CompatiblePositions";

describe("CompatiblePositions", () => {
  it("renders heading and role groups for adapter links", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <CompatiblePositions
          items={[
            {
              role: "drive",
              name: "DA5FU24",
              slug: "da5fu24-d",
              sku_code: "DA5FU24-D",
              category_slug: "elektroprivody",
              image: null,
            },
            {
              role: "valve",
              name: "BV220",
              slug: "8100-bv220a",
              sku_code: "8100-BV220A",
              category_slug: "sharovye-krany",
              image: null,
            },
          ]}
        />
      </MemoryRouter>,
    );
    expect(html).toContain("Совместимые позиции");
    expect(html).toContain("Приводы");
    expect(html).toContain("Краны");
    expect(html).toContain("/catalog/elektroprivody/da5fu24-d");
    expect(html).toContain("/catalog/sharovye-krany/8100-bv220a");
  });

  it("omits subgroup title for bracket-only valve links", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <CompatiblePositions
          items={[
            {
              role: "bracket",
              name: "BR-M",
              slug: "adapter-br-m",
              sku_code: "BR-M",
              category_slug: "adaptery",
              image: null,
            },
          ]}
        />
      </MemoryRouter>,
    );
    expect(html).toContain("Совместимые позиции");
    expect(html).not.toContain("Кронштейн");
    expect(html).toContain("/catalog/adaptery/adapter-br-m");
  });
});
