import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const tsx = readFileSync(join(here, "PhoneField.tsx"), "utf8");
const css = readFileSync(join(here, "PhoneField.module.css"), "utf8");

describe("PhoneField country select sizing", () => {
  it("keeps the number input wider than the country select", () => {
    /*
     * Was: select column minmax(8.5rem, auto) sized to the longest option
     * («Кыргызстан +996») — in narrow lead forms the country select ended up
     * wider than the phone number input. Now the select is a fixed narrow
     * chip and the input takes the flexible track.
     */
    expect(css).toContain("grid-template-columns: auto minmax(0, 1fr)");
    expect(css).not.toContain("minmax(8.5rem, auto)");
    expect(css).toMatch(/\.selectWrap\s*\{[^}]*width:\s*5\.25rem/);
  });

  it("hides the long option label behind a +dial overlay", () => {
    /* Collapsed select shows only «+7»; full names stay in the dropdown. */
    expect(css).toMatch(/\.selectWrap\s+\.country\s*\{[^}]*color:\s*transparent/);
    expect(tsx).toContain("styles.dial");
    expect(tsx).toContain("+{country.dial}");
    expect(css).toMatch(/\.dial\s*\{[^}]*pointer-events:\s*none/);
  });

  it("restores the full country label in the stacked mobile layout", () => {
    const mobile = css.slice(css.indexOf("@media (max-width: 480px)"));
    expect(mobile).toMatch(/\.selectWrap\s+\.country\s*\{[^}]*color:\s*var\(--color-text\)/);
    expect(mobile).toMatch(/\.dial\s*\{[^}]*display:\s*none/);
  });
});
