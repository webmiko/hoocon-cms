import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { criticalFontPreloadHrefs } from "../../vite.font-preload";

describe("fonts loading", () => {
  it("does not chain fontsource through CSS @import", () => {
    const globalCss = readFileSync(
      resolve(import.meta.dirname, "global.css"),
      "utf8",
    );
    expect(globalCss).not.toMatch(/@import\s+["'].*fonts/);
    expect(globalCss).not.toMatch(/@import\s+["']@fontsource/);
  });

  it("preloads cyrillic body and display fonts from the build bundle", () => {
    const hrefs = criticalFontPreloadHrefs({
      "assets/ibm-plex-sans-cyrillic-400-normal-DZqx.woff2": { type: "asset" },
      "assets/montserrat-latin-700-normal-abc.woff2": { type: "asset" },
      "assets/montserrat-cyrillic-700-normal-D-P.woff2": { type: "asset" },
    });
    expect(hrefs).toEqual([
      "/assets/ibm-plex-sans-cyrillic-400-normal-DZqx.woff2",
      "/assets/montserrat-cyrillic-700-normal-D-P.woff2",
    ]);
  });
});
