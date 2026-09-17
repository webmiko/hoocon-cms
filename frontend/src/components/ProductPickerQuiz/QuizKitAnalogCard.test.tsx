import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import { QuizKitAnalogCard } from "./QuizKitAnalogCard";

describe("QuizKitAnalogCard", () => {
  it("renders valve, drive and bracket links for component kit analog", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <QuizKitAnalogCard
          bundle={{
            valve: {
              id: 1,
              name: "Шаровой кран DN 25",
              slug: "8100-bv225a",
              sku_code: "8100-BV225A",
              in_stock: true,
            },
            drive: {
              id: 2,
              name: "DA6MU24-D",
              slug: "da6mu24-d",
              sku_code: "DA6MU24-D",
              in_stock: true,
            },
            bracket: {
              id: 3,
              name: "BR-M",
              slug: "br-m",
              sku_code: "BR-M",
              in_stock: true,
            },
            drive_code: "DA6MU24-D",
            bracket_code: "BR-M",
            in_stock: true,
          }}
        />
      </MemoryRouter>,
    );
    expect(html).toContain("Комплект из отдельных позиций");
    expect(html).toContain("8100-BV225A");
    expect(html).toContain("DA6MU24-D");
    expect(html).toContain("BR-M");
    expect(html).toContain("В наличии");
  });
});
