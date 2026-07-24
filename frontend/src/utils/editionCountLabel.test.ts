import { describe, expect, it } from "vitest";

import { formatEditionCountLabel } from "./editionCountLabel";

describe("formatEditionCountLabel", () => {
  it("hides single-edition cards", () => {
    expect(formatEditionCountLabel(0)).toBe("");
    expect(formatEditionCountLabel(1)).toBe("");
  });

  it("declines 2–4 / 5+ / teens", () => {
    expect(formatEditionCountLabel(2)).toBe("2 варианта");
    expect(formatEditionCountLabel(4)).toBe("4 варианта");
    expect(formatEditionCountLabel(5)).toBe("5 вариантов");
    expect(formatEditionCountLabel(8)).toBe("8 вариантов");
    expect(formatEditionCountLabel(11)).toBe("11 вариантов");
    expect(formatEditionCountLabel(21)).toBe("21 вариант");
    expect(formatEditionCountLabel(22)).toBe("22 варианта");
  });
});
