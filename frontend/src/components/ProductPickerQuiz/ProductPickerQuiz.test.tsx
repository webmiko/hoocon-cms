import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

import { ProductPickerQuiz } from "./ProductPickerQuiz";

describe("ProductPickerQuiz", () => {
  it("renders opening step with plain-language choices", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ProductPickerQuiz />
      </MemoryRouter>,
    );
    expect(html).toContain('id="podbor"');
    expect(html).toContain("Подбор за минуту");
    expect(html).toContain("Что вам нужно?");
    expect(html).toContain("Привод на заслонку или клапан");
    expect(html).toContain("Шаровой кран");
  });
});
