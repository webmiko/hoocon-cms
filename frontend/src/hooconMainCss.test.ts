import { describe, expect, it } from "vitest";

import { HOOCON_MAIN_CSS_ID } from "./hooconMainCss";

describe("HOOCON_MAIN_CSS_ID", () => {
  it("matches the async entry CSS id used by vite.async-css", () => {
    expect(HOOCON_MAIN_CSS_ID).toBe("hoocon-main-css");
  });
});
